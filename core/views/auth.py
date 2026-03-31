import logging

import requests as http_requests
from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken, TokenError

from accounts.models import CustomUser
from core.models import Company, CompanyMember
from core.serializers import UserSerializer

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_company(user):
    """Auto-create a default Company + owner membership if the user has none."""
    if not CompanyMember.objects.filter(user=user).exists():
        company = Company.objects.create(
            name=f"Entreprise de {user.first_name or user.email}",
            owner=user,
        )
        CompanyMember.objects.create(
            company=company,
            user=user,
            role='owner',
        )
    return CompanyMember.objects.filter(user=user).first().company


def _build_auth_response(user, request):
    """Build the standard auth JSON response and set the refresh cookie."""
    _ensure_company(user)
    refresh = RefreshToken.for_user(user)
    data = {
        'user': UserSerializer(user).data,
        'tokens': {
            'access_token': str(refresh.access_token),
        },
    }
    response = Response(data, status=status.HTTP_200_OK)
    response.set_cookie(
        key='refresh_token',
        value=str(refresh),
        httponly=True,
        samesite='Lax',
        secure=False,
        max_age=7 * 24 * 3600,
        path='/',
    )
    return response


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------

@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get('email', '').strip().lower()
    password = request.data.get('password', '')

    if not email or not password:
        return Response(
            {'detail': 'Email and password are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = authenticate(request, username=email, password=password)
    if user is None:
        return Response(
            {'detail': 'Invalid credentials.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    return _build_auth_response(user, request)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    email = request.data.get('email', '').strip().lower()
    password = request.data.get('password', '')
    first_name = request.data.get('first_name', '').strip()
    last_name = request.data.get('last_name', '').strip()

    if not email or not password:
        return Response(
            {'detail': 'Email and password are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if CustomUser.objects.filter(email=email).exists():
        return Response(
            {'detail': 'A user with this email already exists.'},
            status=status.HTTP_409_CONFLICT,
        )

    user = CustomUser.objects.create_user(
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )

    return _build_auth_response(user, request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    response = Response(status=status.HTTP_204_NO_CONTENT)
    response.delete_cookie('refresh_token', path='/')
    return response


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me_view(request):
    user = request.user

    if request.method == 'PATCH':
        first_name = request.data.get('first_name')
        last_name = request.data.get('last_name')
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        user.save(update_fields=['first_name', 'last_name'])

    return Response(UserSerializer(user).data)


@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh_view(request):
    raw_token = request.COOKIES.get('refresh_token')
    if not raw_token:
        return Response(
            {'detail': 'No refresh token.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    try:
        refresh = RefreshToken(raw_token)
        return Response({'access': str(refresh.access_token)})
    except TokenError:
        return Response(
            {'detail': 'Invalid or expired refresh token.'},
            status=status.HTTP_401_UNAUTHORIZED,
        )


@api_view(['POST'])
@permission_classes([AllowAny])
def social_login_view(request):
    provider = request.data.get('provider', '').lower()
    code = request.data.get('code', '')
    redirect_uri = request.data.get('redirect_uri', '')

    if provider not in ('google', 'microsoft'):
        return Response(
            {'detail': 'Unsupported provider. Use "google" or "microsoft".'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not code or not redirect_uri:
        return Response(
            {'detail': 'code and redirect_uri are required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Fetch client credentials from allauth SocialApp
    try:
        from allauth.socialaccount.models import SocialApp
        social_app = SocialApp.objects.get(provider=provider)
        client_id = social_app.client_id
        client_secret = social_app.secret
    except Exception:
        return Response(
            {'detail': f'Social app for {provider} is not configured.'},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # Provider-specific URLs
    if provider == 'google':
        token_url = 'https://oauth2.googleapis.com/token'
        userinfo_url = 'https://www.googleapis.com/oauth2/v3/userinfo'
    else:  # microsoft
        token_url = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'
        userinfo_url = 'https://graph.microsoft.com/v1.0/me'

    # Exchange code for access token
    token_resp = http_requests.post(token_url, data={
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': redirect_uri,
        'client_id': client_id,
        'client_secret': client_secret,
    }, timeout=10)

    if token_resp.status_code != 200:
        logger.error('Social token exchange failed: %s', token_resp.text)
        return Response(
            {'detail': 'Failed to exchange code for token.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    access_token = token_resp.json().get('access_token')

    # Fetch user info
    info_resp = http_requests.get(
        userinfo_url,
        headers={'Authorization': f'Bearer {access_token}'},
        timeout=10,
    )

    if info_resp.status_code != 200:
        logger.error('Social userinfo fetch failed: %s', info_resp.text)
        return Response(
            {'detail': 'Failed to fetch user info from provider.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    info = info_resp.json()

    # Extract email and names (field names differ by provider)
    if provider == 'google':
        social_email = info.get('email', '')
        first_name = info.get('given_name', '')
        last_name = info.get('family_name', '')
        uid = info.get('sub', '')
    else:  # microsoft
        social_email = info.get('mail') or info.get('userPrincipalName', '')
        first_name = info.get('givenName', '')
        last_name = info.get('surname', '')
        uid = info.get('id', '')

    if not social_email:
        return Response(
            {'detail': 'Could not retrieve email from provider.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    social_email = social_email.lower()

    # Get or create Django user
    user, created = CustomUser.objects.get_or_create(
        email=social_email,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
        },
    )
    if not created and not user.first_name:
        user.first_name = first_name
        user.last_name = last_name
        user.save(update_fields=['first_name', 'last_name'])

    # Create SocialAccount link (idempotent)
    try:
        from allauth.socialaccount.models import SocialAccount
        SocialAccount.objects.get_or_create(
            user=user,
            provider=provider,
            defaults={'uid': uid, 'extra_data': info},
        )
    except Exception:
        logger.warning('Could not create SocialAccount link for %s', social_email)

    return _build_auth_response(user, request)


@api_view(['POST'])
@permission_classes([AllowAny])
def clear_session_view(request):
    response = Response(status=status.HTTP_204_NO_CONTENT)
    response.delete_cookie('refresh_token', path='/')
    return response


@api_view(['POST'])
@permission_classes([AllowAny])
def social_auth_url_view(request):
    """Build and return the OAuth authorization URL for Google or Microsoft.
    Keeps client_id server-side — never exposed to the frontend."""
    import urllib.parse
    from allauth.socialaccount.models import SocialApp

    provider = request.data.get('provider', '')
    redirect_uri = request.data.get('redirect_uri', '')

    if provider not in ('google', 'microsoft'):
        return Response({'detail': f'Unknown provider: {provider}'}, status=status.HTTP_400_BAD_REQUEST)

    try:
        app = SocialApp.objects.get(provider=provider)
    except SocialApp.DoesNotExist:
        return Response({'detail': f'{provider} not configured'}, status=status.HTTP_400_BAD_REQUEST)

    if provider == 'google':
        params = urllib.parse.urlencode({
            'client_id': app.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid profile email',
            'access_type': 'online',
            'prompt': 'select_account',
        })
        url = f'https://accounts.google.com/o/oauth2/v2/auth?{params}'
    else:
        params = urllib.parse.urlencode({
            'client_id': app.client_id,
            'redirect_uri': redirect_uri,
            'response_type': 'code',
            'scope': 'openid profile email User.Read',
            'response_mode': 'query',
        })
        url = f'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?{params}'

    return Response({'authorization_url': url})
