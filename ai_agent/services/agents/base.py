"""
Base agent framework: Worker/Verifier/Cleaner pattern with recovery paths.

Inspired by Claude Code architecture (rapport §2.1):
- Immutable state rebuilt at each transition
- Named recovery paths with anti-loop guards
- Circuit breaker per agent
- Model selection: Haiku for simple tasks, Sonnet for complex reasoning
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any

import anthropic
from anthropic import RateLimitError as _RateLimitError, APIError as _APIError
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = getattr(settings, 'AI_MAX_RETRIES', 3)
RETRY_BASE_DELAY = getattr(settings, 'AI_RETRY_BASE_DELAY', 2)
MAX_TURNS_PER_PHASE = 20
MAX_RATE_LIMIT_RETRIES = 3
MAX_TOOL_ERROR_RETRIES = 3


@dataclass(frozen=True)
class PhaseState:
    """Immutable state rebuilt at each transition (rapport §2.1)."""
    phase: str
    turn_count: int = 0
    items_total: int = 0
    items_processed: int = 0
    items_failed: tuple = ()

    # Recovery guards
    rate_limit_retries: int = 0
    token_overflow_retries: int = 0
    tool_error_retries: int = 0
    has_attempted_compaction: bool = False

    # Transition info
    transition_reason: str = ''

    @property
    def can_retry_rate_limit(self) -> bool:
        return self.rate_limit_retries < MAX_RATE_LIMIT_RETRIES

    @property
    def can_retry_tool_error(self) -> bool:
        return self.tool_error_retries < MAX_TOOL_ERROR_RETRIES

    @property
    def has_turns_remaining(self) -> bool:
        return self.turn_count < MAX_TURNS_PER_PHASE

    def transition(self, reason: str = '', **kwargs) -> 'PhaseState':
        """Create a new state with updated fields."""
        updates = {k: v for k, v in kwargs.items() if v is not None}
        updates['transition_reason'] = reason
        return replace(self, **updates)


@dataclass
class AgentResult:
    """Result from an agent phase execution."""
    success: bool
    items_processed: int = 0
    items_failed: int = 0
    stats: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


class CircuitBreaker:
    """
    Stops API calls after consecutive failures (rapport §2.1).
    3 states: CLOSED -> OPEN -> HALF_OPEN.
    """
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'

    def __init__(self, failure_threshold=3, recovery_timeout=60):
        self.state = self.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self._lock = threading.Lock()

    def can_call(self) -> bool:
        with self._lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if self.last_failure_time and (time.time() - self.last_failure_time >= self.recovery_timeout):
                    self.state = self.HALF_OPEN
                    return True
                return False
            return self.state == self.HALF_OPEN

    def record_success(self):
        with self._lock:
            self.failure_count = 0
            self.state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                logger.warning(
                    f'[CircuitBreaker] OPEN after {self.failure_count} failures, '
                    f'blocking for {self.recovery_timeout}s'
                )


class BaseAgent:
    """
    Base class for all pipeline agents.

    Each agent follows the Worker/Verifier/Cleaner pattern:
    - Worker: does the main LLM work
    - Verifier: independent LLM call reviewing worker output (fresh context)
    - Cleaner: post-processing cleanup (dedup, validation)

    Subclasses implement:
    - run_worker(state, context) -> list of results
    - run_verifier(results) -> list of corrections
    - run_cleaner(results, corrections) -> cleaned results
    """

    def __init__(self, client=None, model='claude-haiku-4-5-20251001'):
        self.client = client or anthropic.Anthropic(
            api_key=getattr(settings, 'ANTHROPIC_API_KEY', None)
        )
        self.model = model
        self.circuit_breaker = CircuitBreaker()

    def execute(self, user, context: dict) -> AgentResult:
        """
        Run the full Worker -> Verifier -> Cleaner pipeline.
        Returns AgentResult with stats.
        """
        logger.info(f'[{self.__class__.__name__}] Starting execution')

        # Step 1: Worker produces results
        try:
            worker_results = self.run_worker(user, context)
        except Exception as e:
            logger.error(f'[{self.__class__.__name__}] Worker failed: {e}')
            return AgentResult(success=False, errors=[str(e)])

        # Step 2: Verifier reviews (fresh context, no self-confirmation)
        try:
            corrections = self.run_verifier(user, worker_results, context)
        except Exception as e:
            logger.warning(f'[{self.__class__.__name__}] Verifier failed: {e}, using worker results as-is')
            corrections = []

        # Step 3: Cleaner applies corrections and validates
        try:
            cleaned = self.run_cleaner(user, worker_results, corrections, context)
        except Exception as e:
            logger.warning(f'[{self.__class__.__name__}] Cleaner failed: {e}, using worker results')
            cleaned = worker_results

        return AgentResult(
            success=True,
            items_processed=len(cleaned),
            stats={'worker_results': len(worker_results), 'corrections': len(corrections)},
        )

    def run_worker(self, user, context: dict) -> list:
        raise NotImplementedError

    def run_verifier(self, user, results: list, context: dict) -> list:
        return []  # default: no verification

    def run_cleaner(self, user, results: list, corrections: list, context: dict) -> list:
        return results  # default: no cleaning

    def _call_llm_sync(self, system: str, messages: list, tools: list | None = None,
                       max_tokens: int = 4096, model: str | None = None) -> Any:
        """
        Call the Anthropic API with retry on rate limit errors.
        Uses circuit breaker to prevent cascading failures.
        """
        if not self.circuit_breaker.can_call():
            raise RuntimeError('Circuit breaker is OPEN — too many consecutive failures')

        use_model = model or self.model
        kwargs = {
            'model': use_model,
            'max_tokens': max_tokens,
            'system': system,
            'messages': messages,
        }
        if tools:
            kwargs['tools'] = tools

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(**kwargs)
                self.circuit_breaker.record_success()
                return response
            except _RateLimitError:
                self.circuit_breaker.record_failure()
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f'Rate limited, retrying in {delay}s (attempt {attempt + 1})')
                    time.sleep(delay)
                else:
                    raise
            except _APIError as e:
                self.circuit_breaker.record_failure()
                if getattr(e, 'status_code', 0) == 529 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f'API overloaded, retrying in {delay}s')
                    time.sleep(delay)
                else:
                    raise

    def _extract_text(self, response) -> str:
        """Extract text content from an Anthropic API response."""
        return ''.join(
            block.text for block in response.content
            if hasattr(block, 'text') and block.text
        )

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from LLM response text (handles markdown fences)."""
        import re

        if not text:
            return None

        stripped = text.strip()

        # Try direct parse
        for start_char in ('{', '['):
            if stripped.startswith(start_char):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass

        # Try finding JSON in text
        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Try markdown code block
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _run_agentic_loop(self, system: str, messages: list, tools: list,
                          tool_handlers: dict, max_iterations: int = 15,
                          model: str | None = None) -> tuple[list, dict]:
        """
        Run a tool-use agentic loop (rapport §2.1).

        Returns (messages, stats) where messages is the full conversation
        and stats tracks tool calls and results.
        """
        stats = {'api_calls': 0, 'tool_calls': 0, 'iterations': 0}
        messages = list(messages)  # copy

        response = self._call_llm_sync(
            system=system, messages=messages, tools=tools, model=model,
        )
        stats['api_calls'] += 1

        for iteration in range(max_iterations):
            stats['iterations'] = iteration + 1

            if response.stop_reason != 'tool_use':
                break

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type != 'tool_use':
                    continue

                stats['tool_calls'] += 1
                handler = tool_handlers.get(block.name)

                if handler:
                    try:
                        result = handler(block.input)
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps(result, default=str),
                        })
                    except Exception as e:
                        logger.error(f'Tool error {block.name}: {e}')
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'error': str(e)}),
                            'is_error': True,
                        })
                else:
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps({'error': f'Unknown tool: {block.name}'}),
                        'is_error': True,
                    })

            messages.append({'role': 'assistant', 'content': response.content})
            messages.append({'role': 'user', 'content': tool_results})

            response = self._call_llm_sync(
                system=system, messages=messages, tools=tools, model=model,
            )
            stats['api_calls'] += 1

        return messages, stats
