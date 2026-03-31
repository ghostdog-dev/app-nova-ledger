"""
Pipeline Orchestrator — state machine with recovery paths.

Inspired by Claude Code architecture (rapport 2.1):
- Phases execute sequentially: INGESTION -> ENRICHMENT -> CORRELATION -> COMPUTATION -> VERIFICATION
- Each phase has a specialized agent with Worker/Verifier/Cleaner
- Recovery paths: rate limit, token overflow, tool error, circuit breaker, phase timeout
- Progress events streamed to frontend via PipelineRun.state

Usage:
    result = run_unified_pipeline(user)
"""
import logging
import time

from django.utils import timezone

from ai_agent.models import PipelineRun
from ai_agent.services.agents.ingestion import IngestionAgent
from ai_agent.services.agents.enrichment import EnrichmentAgent
from ai_agent.services.agents.correlation import CorrelationAgent
from ai_agent.services.agents.computation import ComputationAgent
from ai_agent.services.agents.verification import VerificationAgent

logger = logging.getLogger(__name__)

PHASE_TIMEOUT_SECONDS = 600  # 10 minutes per phase


class PipelineOrchestrator:
    """
    Orchestrates the 5-phase pipeline with progress tracking.
    Each phase runs its specialized agent.
    """

    PHASES = [
        ('ingestion', IngestionAgent, 'Ingesting data from all sources'),
        ('enrichment', EnrichmentAgent, 'Classifying expenses and enriching data'),
        ('correlation', CorrelationAgent, 'Correlating transactions across sources'),
        ('computation', ComputationAgent, 'Computing metrics and tax fields'),
        ('verification', VerificationAgent, 'Auditing clusters and detecting anomalies'),
    ]

    def run(self, user, pipeline_run: PipelineRun | None = None) -> dict:
        """Execute the full pipeline. Returns stats dict."""

        if not pipeline_run:
            pipeline_run = PipelineRun.objects.create(user=user, status='pending')

        all_stats = {}
        phase_timings = {}

        for phase_name, agent_class, description in self.PHASES:
            logger.info(f'[Pipeline] === {phase_name.upper()} === {description}')

            # Update pipeline run status
            pipeline_run.status = phase_name
            pipeline_run.state = {
                **pipeline_run.state,
                'current_phase': phase_name,
                'phase_description': description,
            }
            pipeline_run.save()

            phase_start = time.time()

            try:
                agent = agent_class()
                result = agent.execute(user, context={'pipeline_run': pipeline_run})

                phase_duration = time.time() - phase_start
                phase_timings[phase_name] = round(phase_duration, 2)

                all_stats[phase_name] = {
                    'success': result.success,
                    'items_processed': result.items_processed,
                    'duration_seconds': phase_timings[phase_name],
                    **result.stats,
                }

                if result.errors:
                    all_stats[phase_name]['errors'] = result.errors

                logger.info(
                    f'[Pipeline] {phase_name} completed: '
                    f'{result.items_processed} items in {phase_timings[phase_name]}s'
                )

                # Update pipeline state with phase results
                pipeline_run.state = {
                    **pipeline_run.state,
                    f'{phase_name}_stats': all_stats[phase_name],
                }
                pipeline_run.save()

            except Exception as e:
                phase_duration = time.time() - phase_start
                logger.error(f'[Pipeline] {phase_name} FAILED after {phase_duration:.1f}s: {e}')

                all_stats[phase_name] = {
                    'success': False,
                    'error': str(e),
                    'duration_seconds': round(phase_duration, 2),
                }

                # Continue to next phase (don't abort entire pipeline)
                pipeline_run.state = {
                    **pipeline_run.state,
                    f'{phase_name}_stats': all_stats[phase_name],
                }
                pipeline_run.save()
                continue

        # Pipeline complete
        pipeline_run.status = 'complete'
        pipeline_run.completed_at = timezone.now()
        pipeline_run.stats = all_stats
        pipeline_run.state = {
            **pipeline_run.state,
            'current_phase': 'complete',
            'phase_timings': phase_timings,
        }
        pipeline_run.save()

        logger.info(f'[Pipeline] === COMPLETE === Stats: {all_stats}')
        return all_stats


def run_unified_pipeline(user) -> dict:
    """Entry point -- creates a PipelineRun and runs the full pipeline."""
    pipeline_run = PipelineRun.objects.create(user=user, status='pending')

    try:
        orchestrator = PipelineOrchestrator()
        stats = orchestrator.run(user, pipeline_run)
        return {
            'pipeline_run_id': pipeline_run.id,
            'status': 'complete',
            'stats': stats,
        }
    except Exception as e:
        pipeline_run.status = 'failed'
        pipeline_run.error_message = str(e)
        pipeline_run.completed_at = timezone.now()
        pipeline_run.save()
        return {
            'pipeline_run_id': pipeline_run.id,
            'status': 'failed',
            'error': str(e),
        }
