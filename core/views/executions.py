import logging
import threading

from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, Correlation, Execution, ServiceConnection
from core.serializers import CreateExecutionSerializer, ExecutionSerializer

logger = logging.getLogger(__name__)

# Map PipelineRun status to frontend step index
PIPELINE_STEP_MAP = {
    'pending': (0, 'triage'),
    'triage': (0, 'triage'),
    'extraction': (1, 'extraction'),
    'merge': (2, 'merge'),
    'computation': (3, 'computation'),
    'bank_correlation': (4, 'bank_correlation'),
    'provider_correlation': (5, 'provider_correlation'),
    'classification': (6, 'report'),
    'recurring': (6, 'report'),
}

TOTAL_STEPS = 7


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


def _run_pipeline_async(execution, user):
    """Run the AI pipeline in a background thread and update the Execution."""
    from ai_agent.services.pipeline import run_pipeline
    from banking.models import TransactionMatch, ProviderMatch

    try:
        stats = run_pipeline(user)

        if 'error' in stats:
            execution.status = 'failed'
            execution.error_message = stats['error']
            execution.date_end = timezone.now()
            execution.duration_seconds = (
                execution.date_end - execution.date_start
            ).total_seconds()
            execution.save()
            return

        # Build Correlation records from TransactionMatch + ProviderMatch
        matches = TransactionMatch.objects.filter(
            user=user, status='auto',
        ).select_related('bank_transaction', 'email_transaction')

        for m in matches:
            etx = m.email_transaction
            btx = m.bank_transaction

            invoice_data = {
                'numero': etx.invoice_number or etx.order_number or '',
                'dateEmission': str(etx.transaction_date) if etx.transaction_date else '',
                'fournisseur': etx.vendor_name,
                'montantHt': str(etx.amount_tax_excl) if etx.amount_tax_excl else '',
                'montantTtc': str(etx.amount) if etx.amount else '',
                'devise': etx.currency,
                'type': etx.type,
                'taxAmount': str(etx.tax_amount) if etx.tax_amount else '',
                'taxRate': str(etx.tax_rate) if etx.tax_rate else '',
            }

            payment_data = {
                'reference': str(btx.powens_transaction_id) if btx.powens_transaction_id else '',
                'date': str(btx.date) if btx.date else '',
                'montant': str(abs(btx.value)) if btx.value else '',
                'devise': btx.original_currency or btx.account.currency,
                'methode': btx.transaction_type or '',
                'libelle': btx.simplified_wording or btx.original_wording or '',
            }

            # Determine statut
            if m.confidence >= 0.80:
                statut = 'reconciled'
            elif m.confidence >= 0.60:
                statut = 'reconciled_with_alert'
            else:
                statut = 'uncertain'

            Correlation.objects.create(
                execution=execution,
                invoice_data=invoice_data,
                payment_data=payment_data,
                score_confiance=m.confidence,
                statut=statut,
                match_criteria=m.match_method,
            )

        # Unmatched email transactions → unpaid
        from emails.models import Transaction as EmailTransaction
        matched_email_ids = set(matches.values_list('email_transaction_id', flat=True))
        unmatched = EmailTransaction.objects.filter(
            user=user, status='complete',
        ).exclude(id__in=matched_email_ids)

        for etx in unmatched:
            if not etx.amount:
                continue
            Correlation.objects.create(
                execution=execution,
                invoice_data={
                    'numero': etx.invoice_number or etx.order_number or '',
                    'dateEmission': str(etx.transaction_date) if etx.transaction_date else '',
                    'fournisseur': etx.vendor_name,
                    'montantHt': str(etx.amount_tax_excl) if etx.amount_tax_excl else '',
                    'montantTtc': str(etx.amount) if etx.amount else '',
                    'devise': etx.currency,
                    'type': etx.type,
                },
                payment_data=None,
                score_confiance=0,
                statut='unpaid',
                match_criteria='',
            )

        # Summary
        total_correlations = execution.correlations.count()
        matched_count = execution.correlations.exclude(statut='unpaid').count()
        rate = round(matched_count / total_correlations * 100) if total_correlations else 0

        execution.status = 'completed'
        execution.summary = {
            'invoices_processed': stats.get('triage_transactional', 0),
            'correlations_found': matched_count,
            'anomalies_detected': 0,
            'reconciliation_rate': rate,
            'bank_matched': stats.get('bank_matched', 0),
            'bank_unmatched': stats.get('bank_unmatched', 0),
            'extraction_created': stats.get('extraction_transactions_created', 0),
            'provider_stripe': stats.get('provider_stripe_matched', 0),
            'provider_paypal': stats.get('provider_paypal_matched', 0),
            'provider_mollie': stats.get('provider_mollie_matched', 0),
        }
        execution.date_end = timezone.now()
        execution.duration_seconds = (
            execution.date_end - execution.date_start
        ).total_seconds()
        execution.save()
        logger.info(f'Execution {execution.public_id} completed: {execution.summary}')

    except Exception as e:
        logger.exception(f'Execution {execution.public_id} failed')
        execution.status = 'failed'
        execution.error_message = str(e)
        execution.date_end = timezone.now()
        execution.duration_seconds = (
            execution.date_end - execution.date_start
        ).total_seconds()
        execution.save()


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def execution_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        # Include new PipelineRun entries alongside old Executions
        from ai_agent.models import PipelineRun
        pipeline_runs = PipelineRun.objects.filter(user=request.user).order_by('-started_at')

        # Convert PipelineRun to execution-like format
        pipeline_results = []
        for run in pipeline_runs:
            duration = None
            if run.completed_at and run.started_at:
                duration = (run.completed_at - run.started_at).total_seconds()

            status_map = {'complete': 'completed', 'failed': 'failed', 'pending': 'pending'}
            mapped_status = status_map.get(run.status, 'running')

            pipeline_results.append({
                'publicId': str(run.pk),
                'dateFrom': run.started_at.strftime('%Y-%m-%d') if run.started_at else '',
                'dateTo': run.completed_at.strftime('%Y-%m-%d') if run.completed_at else run.started_at.strftime('%Y-%m-%d') if run.started_at else '',
                'status': mapped_status,
                'durationSeconds': round(duration) if duration else 0,
                'createdAt': run.started_at.isoformat() if run.started_at else '',
                'errorMessage': run.error_message or '',
                'summary': {
                    'invoicesProcessed': run.stats.get('enrichment', {}).get('items_processed', 0) if run.stats else 0,
                    'correlationsFound': run.stats.get('correlation', {}).get('clusters_created', 0) if run.stats else 0,
                    'anomaliesDetected': run.stats.get('verification', {}).get('anomalies_total', 0) if run.stats else 0,
                    'reconciliationRate': 0,
                } if run.stats else None,
                'pipelineType': 'unified',
            })

        # Old executions
        executions = company.executions.select_related('company', 'user').order_by('-created_at')
        serializer = ExecutionSerializer(executions, many=True)
        old_results = serializer.data

        # Merge: pipeline runs first, then old executions
        all_results = pipeline_results + old_results
        return Response({'count': len(all_results), 'results': all_results})

    # POST — create execution and launch pipeline
    serializer = CreateExecutionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    execution = Execution.objects.create(
        company=company,
        user=request.user,
        date_from=data['date_from'],
        date_to=data['date_to'],
        granularity=data.get('granularity', 'invoice_payment'),
        parameters=data.get('parameters', {}),
        status='running',
        date_start=timezone.now(),
    )

    included_connections = data.get('included_connections', [])
    if included_connections:
        connections = ServiceConnection.objects.filter(
            company=company,
            public_id__in=included_connections,
        )
        execution.included_connections.set(connections)

    # Launch pipeline in background thread
    thread = threading.Thread(
        target=_run_pipeline_async,
        args=(execution, request.user),
        daemon=True,
    )
    thread.start()

    return Response(
        ExecutionSerializer(execution).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def execution_detail_view(request, company_pk, execution_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.select_related('company', 'user').get(
            public_id=execution_pk,
        )
    except Execution.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    return Response(ExecutionSerializer(execution).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def execution_progress_view(request, company_pk, execution_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.get(public_id=execution_pk)
    except Execution.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if execution.status == 'completed':
        return Response({
            'type': 'completed',
            'summary': execution.summary,
        })

    if execution.status == 'failed':
        return Response({
            'type': 'failed',
            'error': execution.error_message,
        })

    # Read real progress from PipelineRun
    from ai_agent.models import PipelineRun
    pipeline_run = PipelineRun.objects.filter(
        user=request.user,
    ).exclude(
        status__in=[PipelineRun.Status.COMPLETE, PipelineRun.Status.FAILED],
    ).order_by('-started_at').first()

    if pipeline_run:
        step_index, step_id = PIPELINE_STEP_MAP.get(
            pipeline_run.status, (0, 'triage'),
        )
        percentage = round((step_index / TOTAL_STEPS) * 100)
        return Response({
            'type': 'progress',
            'step': step_id,
            'stepIndex': step_index,
            'totalSteps': TOTAL_STEPS,
            'percentage': percentage,
            'message': f'{step_id}...',
        })

    # Pipeline not started yet
    return Response({
        'type': 'progress',
        'step': 'triage',
        'stepIndex': 0,
        'totalSteps': TOTAL_STEPS,
        'percentage': 0,
        'message': 'Démarrage...',
    })
