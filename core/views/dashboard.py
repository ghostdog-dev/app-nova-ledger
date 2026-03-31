from django.db.models import Count
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from core.models import Company, Execution, ServiceConnection
from core.serializers import ExecutionSerializer, ServiceConnectionSerializer


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    # Last execution
    last_execution = (
        company.executions
        .select_related('company', 'user')
        .order_by('-created_at')
        .first()
    )

    # Stats
    reconciliation_rate = 0.0
    total_invoices = 0
    anomalies_count = 0
    if last_execution and last_execution.summary:
        reconciliation_rate = last_execution.summary.get('reconciliation_rate', 0)
        total_invoices = last_execution.summary.get('invoices_processed', 0)
        anomalies_count = last_execution.summary.get('anomalies_detected', 0)

    connected_services = company.connections.count()

    stats = {
        'reconciliation_rate': reconciliation_rate,
        'total_invoices': total_invoices,
        'anomalies': anomalies_count,
        'connected_services': connected_services,
    }

    # Correlation distribution from last execution
    correlation_distribution = []
    if last_execution:
        distribution = (
            last_execution.correlations
            .values('statut')
            .annotate(count=Count('id'))
            .order_by('statut')
        )
        correlation_distribution = [
            {'status': entry['statut'], 'count': entry['count']}
            for entry in distribution
        ]

    # Alerts from connections with error or expired status
    problem_connections = company.connections.filter(status__in=['error', 'expired'])
    alerts = [
        {
            'type': conn.status,
            'provider': conn.provider_name,
            'service_type': conn.service_type,
            'message': conn.error_message or f'Connection {conn.status}',
            'public_id': str(conn.public_id),
        }
        for conn in problem_connections
    ]

    # Recent transactions (empty for now, populated by transactions view)
    recent_transactions = {'transactions': [], 'total_count': 0}

    # Connections
    connections = company.connections.all()

    data = {
        'stats': stats,
        'correlation_distribution': correlation_distribution,
        'monthly_evolution': [],
        'alerts': alerts,
        'last_execution': ExecutionSerializer(last_execution).data if last_execution else None,
        'recent_transactions': recent_transactions,
        'connections': ServiceConnectionSerializer(connections, many=True).data,
    }

    return Response(data)
