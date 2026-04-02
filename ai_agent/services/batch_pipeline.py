"""
Batch pipeline using Anthropic Message Batches API.

For scheduled/nightly runs where real-time results aren't needed.
50% cost reduction vs interactive API.

Usage:
  POST /api/ai/classify-batch/  -> submit batch, returns pipeline_run_id
  GET /api/ai/classify-batch/<run_id>/  -> poll results
"""
import json
import logging
import os

import anthropic
from django.conf import settings
from django.utils import timezone

from ai_agent.models import PipelineRun
from ai_agent.services.pipeline import (
    TRIAGE_WORKER_PROMPT,
    _get_api_key,
    _run_computation_pass,
    _run_bank_correlation,
    _run_provider_correlation,
)
from banking.models import BankTransaction, TransactionMatch
from emails.models import Email, Transaction

logger = logging.getLogger(__name__)

MODEL_TRIAGE = settings.AI_MODEL_TRIAGE
MODEL_CLASSIFICATION = settings.AI_MODEL_CLASSIFICATION


def submit_batch_pipeline(user):
    """
    Submit triage + classification as batch requests.
    Returns PipelineRun with batch IDs stored in state.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    client = anthropic.Anthropic(api_key=api_key)

    pipeline_run = PipelineRun.objects.create(
        user=user,
        status=PipelineRun.Status.PENDING,
        state={"mode": "batch"},
    )

    # Prepare triage requests
    new_emails = list(
        Email.objects.filter(user=user, status=Email.Status.NEW)
        .order_by('-date')
        .values('id', 'from_address', 'subject', 'snippet', 'date')
    )

    if not new_emails:
        pipeline_run.status = PipelineRun.Status.COMPLETE
        pipeline_run.completed_at = timezone.now()
        pipeline_run.stats = {'triage_total': 0, 'message': 'No new emails'}
        pipeline_run.save()
        return {
            'pipeline_run_id': pipeline_run.pk,
            'status': 'complete',
            'message': 'No new emails',
        }

    # Build triage batch requests (one per batch of 40)
    triage_batch_size = settings.AI_TRIAGE_BATCH_SIZE
    triage_requests = []

    for i in range(0, len(new_emails), triage_batch_size):
        batch_emails = new_emails[i:i + triage_batch_size]
        email_lines = []
        for e in batch_emails:
            email_lines.append(
                f'- id={e["id"]}, from="{e["from_address"]}", '
                f'subject="{e["subject"]}", '
                f'snippet="{(e["snippet"] or "")[:120]}", '
                f'date="{e["date"]}"'
            )
        emails_text = "\n".join(email_lines)

        triage_requests.append({
            "custom_id": f"triage-batch-{i}",
            "params": {
                "model": MODEL_TRIAGE,
                "max_tokens": 2048,
                "system": [{
                    "type": "text",
                    "text": TRIAGE_WORKER_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }],
                "messages": [{
                    "role": "user",
                    "content": f"Emails ({len(batch_emails)}):\n{emails_text}",
                }],
            },
        })

    # Submit triage batch
    try:
        triage_batch = client.messages.batches.create(requests=triage_requests)
        pipeline_run.state['triage_batch_id'] = triage_batch.id
        pipeline_run.state['triage_email_count'] = len(new_emails)
        pipeline_run.status = PipelineRun.Status.TRIAGE
        pipeline_run.save()

        logger.info(
            f'[BatchPipeline] Submitted triage batch {triage_batch.id} '
            f'with {len(triage_requests)} requests for {len(new_emails)} emails'
        )

        return {
            'pipeline_run_id': pipeline_run.pk,
            'status': 'submitted',
            'triage_batch_id': triage_batch.id,
            'email_count': len(new_emails),
        }
    except Exception as e:
        pipeline_run.status = PipelineRun.Status.FAILED
        pipeline_run.error_message = str(e)
        pipeline_run.save()
        logger.error(f'[BatchPipeline] Failed to submit triage batch: {e}')
        return {'error': str(e), 'pipeline_run_id': pipeline_run.pk}


def poll_batch_pipeline(pipeline_run_id, user):
    """
    Poll the status of a batch pipeline run.
    Processes results when batches complete, advances to next stage.
    """
    try:
        pipeline_run = PipelineRun.objects.get(pk=pipeline_run_id, user=user)
    except PipelineRun.DoesNotExist:
        return {'error': 'Pipeline run not found'}

    if pipeline_run.status == PipelineRun.Status.COMPLETE:
        return {'status': 'complete', 'stats': pipeline_run.stats}

    if pipeline_run.status == PipelineRun.Status.FAILED:
        return {'status': 'failed', 'error': pipeline_run.error_message}

    api_key = _get_api_key()
    if not api_key:
        return {'error': 'ANTHROPIC_API_KEY not configured'}

    client = anthropic.Anthropic(api_key=api_key)

    # Check triage batch
    if pipeline_run.status == PipelineRun.Status.TRIAGE:
        triage_batch_id = pipeline_run.state.get('triage_batch_id')
        if not triage_batch_id:
            return {'status': 'error', 'message': 'No triage batch ID found'}

        batch_status = client.messages.batches.retrieve(triage_batch_id)

        if batch_status.processing_status == 'ended':
            # Process triage results
            stats = _process_triage_batch_results(
                client, triage_batch_id, user
            )
            pipeline_run.stats.update(stats)

            # Run remaining passes synchronously (they're fast/Python-only)
            # Pass 4: Computation
            comp_stats = _run_computation_pass(user)
            pipeline_run.stats.update(comp_stats)

            # Pass 5: Bank correlation
            bank_stats = _run_bank_correlation(user)
            pipeline_run.stats.update(bank_stats)

            # Pass 6: Provider correlation
            provider_stats = _run_provider_correlation(user)
            pipeline_run.stats.update(provider_stats)

            pipeline_run.status = PipelineRun.Status.COMPLETE
            pipeline_run.completed_at = timezone.now()
            pipeline_run.save()

            return {'status': 'complete', 'stats': pipeline_run.stats}
        else:
            counts = batch_status.request_counts
            return {
                'status': 'processing',
                'stage': 'triage',
                'batch_id': triage_batch_id,
                'processing_status': batch_status.processing_status,
                'succeeded': counts.succeeded,
                'errored': counts.errored,
                'expired': counts.expired,
                'processing': counts.processing,
            }

    return {'status': pipeline_run.status, 'message': 'Unknown state'}


def _process_triage_batch_results(client, batch_id, user):
    """Process completed triage batch results."""
    transactional_ids = []
    ignored_ids = []

    for result in client.messages.batches.results(batch_id):
        if result.result.type == 'succeeded':
            try:
                text = result.result.message.content[0].text
                data = json.loads(text)
                decisions = data.get('decisions', [])
                for d in decisions:
                    if d.get('transactional'):
                        transactional_ids.append(d['id'])
                    else:
                        ignored_ids.append(d['id'])
            except (json.JSONDecodeError, KeyError, IndexError) as e:
                logger.warning(
                    f'[BatchPipeline] Error parsing triage result '
                    f'{result.custom_id}: {e}'
                )
        else:
            logger.warning(
                f'[BatchPipeline] Triage request {result.custom_id} '
                f'failed: {result.result.type}'
            )

    # Update email statuses
    if ignored_ids:
        Email.objects.filter(
            user=user, id__in=ignored_ids
        ).update(status=Email.Status.IGNORED)
    if transactional_ids:
        Email.objects.filter(
            user=user, id__in=transactional_ids
        ).update(status=Email.Status.TRIAGE_PASSED)

    logger.info(
        f'[BatchPipeline] Triage results: {len(transactional_ids)} '
        f'transactional, {len(ignored_ids)} ignored'
    )

    return {
        'triage_transactional': len(transactional_ids),
        'triage_ignored': len(ignored_ids),
        'triage_total': len(transactional_ids) + len(ignored_ids),
    }
