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
def connection_sync_view(request, company_pk, connection_pk):
    """Trigger a manual data sync for a connection."""
    from django.utils import timezone

    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        connection = ServiceConnection.objects.get(company=company, public_id=connection_pk)
    except (ServiceConnection.DoesNotExist, ValueError):
        return Response({'detail': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    result = {'provider': connection.provider_name, 'status': 'ok', 'details': {}}

    try:
        if connection.provider_name == 'gmail':
            from emails.services import gmail_fetcher
            count = gmail_fetcher.fetch_emails(request.user)
            result['details'] = {'emails_fetched': count}

        elif connection.provider_name == 'outlook':
            from emails.services import microsoft_fetcher
            count = microsoft_fetcher.fetch_emails(request.user)
            result['details'] = {'emails_fetched': count}

        elif connection.provider_name == 'stripe':
            from stripe_provider.views import StripeSyncView
            result['details'] = _call_provider_sync(StripeSyncView, request)

        elif connection.provider_name == 'paypal':
            from paypal_provider.views import PayPalSyncView
            result['details'] = _call_provider_sync(PayPalSyncView, request)

        elif connection.provider_name == 'mollie':
            from mollie_provider.views import MollieSyncView
            result['details'] = _call_provider_sync(MollieSyncView, request)

        else:
            # Generic: try to import {provider}_provider.views.{Provider}SyncView
            provider = connection.provider_name
            try:
                import importlib
                module = importlib.import_module(f'{provider}_provider.views')
                cls_name = f'{provider.title().replace("_", "")}SyncView'
                sync_class = getattr(module, cls_name)
                result['details'] = _call_provider_sync(sync_class, request)
            except (ImportError, AttributeError):
                result['details'] = {'message': f'Sync not yet implemented for {provider}'}

        connection.last_sync = timezone.now()
        connection.status = 'active'
        connection.error_message = ''
        connection.save()

    except Exception as e:
        connection.status = 'error'
        connection.error_message = str(e)
        connection.save()
        result['status'] = 'error'
        result['details'] = {'error': str(e)}

    return Response(result)


def _call_provider_sync(view_class, request):
    """Call an existing provider SyncView and return its response data."""
    from django.test import RequestFactory
    factory = RequestFactory()
    fake_request = factory.post('/fake/', content_type='application/json')
    fake_request.user = request.user
    view = view_class.as_view()
    response = view(fake_request)
    return response.data if hasattr(response, 'data') else {}


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_initiate_view(request, company_pk):
    """Build OAuth authorization URL for email providers (gmail/outlook).
    Uses the same SocialApp credentials as social login."""
    import secrets
    import urllib.parse

    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    provider_name = request.data.get('provider_name', '')
    redirect_uri = request.data.get('redirect_uri', '')

    # Map provider names to allauth provider keys
    provider_map = {'gmail': 'google', 'outlook': 'microsoft'}
    allauth_provider = provider_map.get(provider_name)

    if not allauth_provider:
        return Response(
            {'detail': f'OAuth not supported for {provider_name}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        from allauth.socialaccount.models import SocialApp
        app = SocialApp.objects.get(provider=allauth_provider)
    except Exception:
        return Response(
            {'detail': f'{provider_name} OAuth not configured'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    state = secrets.token_urlsafe(32)

    if allauth_provider == 'google':
        params = urllib.parse.urlencode({
            'client_id': app.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile https://www.googleapis.com/auth/gmail.readonly',
            'access_type': 'offline',
            'prompt': 'consent',
            'state': state,
        })
        url = f'https://accounts.google.com/o/oauth2/v2/auth?{params}'
    else:
        params = urllib.parse.urlencode({
            'client_id': app.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid email profile User.Read Mail.Read offline_access',
            'response_mode': 'query',
            'state': state,
        })
        url = f'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{params}'

    return Response({'authorization_url': url, 'state': state})


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_complete_view(request, company_pk):
    """Complete OAuth flow: exchange code for token, create ServiceConnection."""
    import requests as http_requests

    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    provider_name = request.data.get('provider_name', '')
    code = request.data.get('code', '')
    redirect_uri = request.data.get('redirect_uri', '')

    provider_map = {'gmail': 'google', 'outlook': 'microsoft'}
    allauth_provider = provider_map.get(provider_name)

    if not allauth_provider or not code:
        return Response({'detail': 'Missing provider_name or code'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        from allauth.socialaccount.models import SocialApp
        app = SocialApp.objects.get(provider=allauth_provider)
    except Exception:
        return Response({'detail': f'{provider_name} not configured'}, status=status.HTTP_400_BAD_REQUEST)

    # Exchange code for tokens
    if allauth_provider == 'google':
        token_url = 'https://oauth2.googleapis.com/token'
    else:
        token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'

    token_resp = http_requests.post(token_url, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': app.client_id,
        'client_secret': app.secret,
    }, timeout=10)

    if token_resp.status_code != 200:
        return Response({'detail': 'Failed to exchange code for token'}, status=status.HTTP_400_BAD_REQUEST)

    tokens = token_resp.json()

    # Create or update ServiceConnection
    connection, _ = ServiceConnection.objects.update_or_create(
        company=company,
        provider_name=provider_name,
        defaults={
            'service_type': 'email',
            'auth_type': 'oauth',
            'status': 'active',
            'credentials': {
                'access_token': tokens.get('access_token', ''),
                'refresh_token': tokens.get('refresh_token', ''),
            },
        },
    )

    return Response(ServiceConnectionSerializer(connection).data, status=status.HTTP_201_CREATED)
