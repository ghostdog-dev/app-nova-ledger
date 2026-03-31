from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, Execution, ServiceConnection
from core.serializers import CreateExecutionSerializer, ExecutionSerializer


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def execution_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        executions = (
            company.executions
            .select_related('company', 'user')
            .order_by('-created_at')
        )
        serializer = ExecutionSerializer(executions, many=True)
        return Response({'count': executions.count(), 'results': serializer.data})

    # POST - create execution
    serializer = CreateExecutionSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data

    now = timezone.now()
    summary = {
        'invoices_processed': 0,
        'correlations_found': 0,
        'anomalies_detected': 0,
        'reconciliation_rate': 0,
    }

    execution = Execution.objects.create(
        company=company,
        user=request.user,
        date_from=data['date_from'],
        date_to=data['date_to'],
        granularity=data.get('granularity', 'invoice_payment'),
        parameters=data.get('parameters', {}),
        status='completed',
        summary=summary,
        date_start=now,
        date_end=now,
        duration_seconds=0,
    )

    # Link included_connections by public_id
    included_connections = data.get('included_connections', [])
    if included_connections:
        connections = ServiceConnection.objects.filter(
            company=company,
            public_id__in=included_connections,
        )
        execution.included_connections.set(connections)

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

    # pending or running
    return Response({
        'type': 'progress',
        'step': 'correlation',
        'step_index': 3,
        'total_steps': 6,
        'percentage': 50,
        'message': 'Analysing correlations...',
    })
