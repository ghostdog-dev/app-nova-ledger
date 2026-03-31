from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, CompanyMember, ServiceConnection
from core.serializers import ServiceConnectionSerializer
from core.services.provider_registry import get_provider_config


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


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def connection_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'GET':
        connections = ServiceConnection.objects.filter(company=company)
        serializer = ServiceConnectionSerializer(connections, many=True)
        return Response({'count': connections.count(), 'results': serializer.data})

    # POST — connect via API key
    provider_name = request.data.get('provider_name')
    service_type = request.data.get('service_type')
    auth_type = request.data.get('auth_type', 'api_key')
    credentials = request.data.get('credentials', {})

    if not provider_name:
        return Response(
            {'error': 'provider_name is required'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    config = get_provider_config(provider_name)
    if not config:
        return Response(
            {'error': f'Unknown provider: {provider_name}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    connection, _created = ServiceConnection.objects.update_or_create(
        company=company,
        provider_name=provider_name,
        defaults={
            'service_type': service_type or config['service_type'],
            'auth_type': auth_type or config['auth_type'],
            'credentials': credentials,
            'status': 'active',
        },
    )
    serializer = ServiceConnectionSerializer(connection)
    return Response(serializer.data, status=status.HTTP_201_CREATED)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def connection_check_view(request, company_pk, connection_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        connection = ServiceConnection.objects.get(
            company=company, public_id=connection_pk,
        )
    except (ServiceConnection.DoesNotExist, ValueError):
        return Response(
            {'error': 'Connection not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response({'ok': connection.status == 'active'})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def connection_delete_view(request, company_pk, connection_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    try:
        connection = ServiceConnection.objects.get(
            company=company, public_id=connection_pk,
        )
    except (ServiceConnection.DoesNotExist, ValueError):
        return Response(
            {'error': 'Connection not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    connection.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_initiate_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    provider_name = request.data.get('provider_name', 'unknown')
    return Response(
        {'error': f'OAuth not yet configured for {provider_name}'},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_complete_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response(
            {'error': 'Company not found or access denied'},
            status=status.HTTP_404_NOT_FOUND,
        )

    return Response(
        {'error': 'OAuth completion not yet configured'},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )
