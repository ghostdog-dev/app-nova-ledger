# ai_agent/tests/test_agents.py
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from django.test import TestCase

from ai_agent.services.agents.base import BaseAgent, AgentResult, PhaseState


class PhaseStateTest(TestCase):

    def test_immutable_transition(self):
        state = PhaseState(phase='enrichment', turn_count=0, items_total=10)
        new_state = state.transition(turn_count=1, reason='next_turn')
        self.assertEqual(state.turn_count, 0)  # original unchanged
        self.assertEqual(new_state.turn_count, 1)
        self.assertEqual(new_state.transition_reason, 'next_turn')

    def test_recovery_guards(self):
        state = PhaseState(phase='correlation', turn_count=0, items_total=5)
        self.assertTrue(state.can_retry_rate_limit)
        state2 = state.transition(rate_limit_retries=3, reason='rate_limit')
        self.assertFalse(state2.can_retry_rate_limit)

    def test_max_turns(self):
        state = PhaseState(phase='test', turn_count=20, items_total=1)
        self.assertFalse(state.has_turns_remaining)


class BaseAgentTest(TestCase):

    @patch('ai_agent.services.agents.base.anthropic')
    def test_call_llm_with_retry_rate_limit(self, mock_anthropic):
        """Rate limit error should be retried with backoff."""
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            real_anthropic.RateLimitError(
                message='rate limited',
                response=MagicMock(status_code=429, headers={}),
                body={'error': {'message': 'rate limited', 'type': 'rate_limit_error'}},
            ),
            MagicMock(
                content=[MagicMock(type='text', text='ok')],
                stop_reason='end_turn',
                usage=MagicMock(input_tokens=100, output_tokens=50),
            ),
        ]
        agent = BaseAgent(client=mock_client, model='claude-haiku-4-5-20251001')
        result = agent._call_llm_sync(
            system='test', messages=[{'role': 'user', 'content': 'hi'}]
        )
        self.assertEqual(mock_client.messages.create.call_count, 2)

    @patch('ai_agent.services.agents.base.anthropic')
    def test_circuit_breaker_opens(self, mock_anthropic):
        """3 consecutive failures should open the circuit breaker."""
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = real_anthropic.APIStatusError(
            message='server error',
            response=MagicMock(status_code=500, headers={}),
            body={'error': {'message': 'server error', 'type': 'api_error'}},
        )
        agent = BaseAgent(client=mock_client, model='claude-haiku-4-5-20251001')
        # After 3 failures, circuit breaker should be open
        for _ in range(3):
            try:
                agent._call_llm_sync(
                    system='test', messages=[{'role': 'user', 'content': 'hi'}]
                )
            except Exception:
                pass
        self.assertFalse(agent.circuit_breaker.can_call())
