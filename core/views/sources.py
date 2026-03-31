from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, CompanyMember, ServiceConnection


def _get_company(user, company_pk):
    """Get a company by public_id if the user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except (Company.DoesNotExist, ValueError):
        return None

    is_member = CompanyMember.objects.filter(
        company=company, user=user, is_active=True,
    ).exists()

    if is_member or company.owner == user:
        return company
    return None


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def connection_data_view(request, company_pk, connection_pk):
    """Return fetched data for a specific connection."""
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        connection = ServiceConnection.objects.get(company=company, public_id=connection_pk)
    except (ServiceConnection.DoesNotExist, ValueError):
        return Response({'detail': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    provider = connection.provider_name
    service_type = connection.service_type
    last_sync = connection.last_sync.isoformat() if connection.last_sync else None

    # Email providers — return emails
    if provider in ('gmail', 'outlook'):
        from emails.models import Email

        provider_map = {'gmail': 'google', 'outlook': 'microsoft'}
        emails = Email.objects.filter(
            user=request.user,
            provider=provider_map.get(provider, provider),
        ).order_by('-date')[:50]

        items = [
            {
                'id': e.id,
                'subject': e.subject,
                'sender': e.from_address,
                'date': e.date.isoformat(),
                'status': e.status,
                'body_preview': e.snippet,
            }
            for e in emails
        ]

        return Response({
            'provider_name': provider,
            'service_type': service_type,
            'last_sync': last_sync,
            'items': items,
            'total_count': Email.objects.filter(
                user=request.user,
                provider=provider_map.get(provider, provider),
            ).count(),
        })

    # Other providers — placeholder
    return Response({
        'provider_name': provider,
        'service_type': service_type,
        'last_sync': last_sync,
        'items': [],
        'total_count': 0,
        'message': f'Data view coming soon for {provider}',
    })
