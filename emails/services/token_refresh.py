import logging
from datetime import timedelta

import requests
from allauth.socialaccount.models import SocialAccount, SocialApp, SocialToken
from django.utils import timezone

logger = logging.getLogger(__name__)

GOOGLE_TOKEN_URL = 'https://oauth2.googleapis.com/token'
MICROSOFT_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token'


def _get_social_token(user, provider):
    """Get the SocialToken for a user and provider, or None."""
    try:
        account = SocialAccount.objects.get(user=user, provider=provider)
        return SocialToken.objects.get(account=account)
    except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
        return None


def _get_social_app(provider):
    """Get the SocialApp (client_id/secret) for a provider from the DB."""
    try:
        return SocialApp.objects.get(provider=provider)
    except SocialApp.DoesNotExist:
        logger.error(f'No SocialApp found in DB for provider {provider}')
        return None


def refresh_google_token(user):
    """
    Refresh the Google OAuth access token if expired.
    Returns the valid access token string, or None on failure.
    """
    token = _get_social_token(user, 'google')
    if not token:
        logger.warning(f'No Google token found for user {user.pk}')
        return None

    # Check if token is still valid (with 60s buffer)
    if token.expires_at and token.expires_at > timezone.now() + timedelta(seconds=60):
        return token.token

    # Token is expired or about to expire — refresh it
    refresh_token = token.token_secret
    if not refresh_token:
        logger.error(f'No refresh token (token_secret) for Google user {user.pk}')
        return None

    app = _get_social_app('google')
    if not app:
        return None

    try:
        resp = requests.post(GOOGLE_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'client_id': app.client_id,
            'client_secret': app.secret,
            'refresh_token': refresh_token,
        }, timeout=10)

        if resp.status_code != 200:
            logger.error(
                f'Google token refresh failed for user {user.pk}: '
                f'{resp.status_code} {resp.text[:200]}'
            )
            return None

        data = resp.json()
        new_access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)

        if not new_access_token:
            logger.error(f'Google token refresh returned no access_token for user {user.pk}')
            return None

        # Update token in DB
        token.token = new_access_token
        token.expires_at = timezone.now() + timedelta(seconds=expires_in)
        token.save()

        logger.info(
            f'Refreshed Google token for user {user.pk}, '
            f'new expiry: {token.expires_at.isoformat()}'
        )
        return new_access_token

    except requests.RequestException as e:
        logger.error(f'Google token refresh request failed for user {user.pk}: {e}')
        return None


def refresh_microsoft_token(user):
    """
    Refresh the Microsoft OAuth access token if expired.
    Returns the valid access token string, or None on failure.
    """
    token = _get_social_token(user, 'microsoft')
    if not token:
        logger.warning(f'No Microsoft token found for user {user.pk}')
        return None

    # Check if token is still valid (with 60s buffer)
    if token.expires_at and token.expires_at > timezone.now() + timedelta(seconds=60):
        return token.token

    # Token is expired or about to expire — refresh it
    refresh_token = token.token_secret
    if not refresh_token:
        logger.error(f'No refresh token (token_secret) for Microsoft user {user.pk}')
        return None

    app = _get_social_app('microsoft')
    if not app:
        return None

    try:
        resp = requests.post(MICROSOFT_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'client_id': app.client_id,
            'client_secret': app.secret,
            'refresh_token': refresh_token,
            'scope': 'openid email profile User.Read Mail.Read offline_access',
        }, timeout=10)

        if resp.status_code != 200:
            logger.error(
                f'Microsoft token refresh failed for user {user.pk}: '
                f'{resp.status_code} {resp.text[:200]}'
            )
            return None

        data = resp.json()
        new_access_token = data.get('access_token')
        expires_in = data.get('expires_in', 3600)

        if not new_access_token:
            logger.error(f'Microsoft token refresh returned no access_token for user {user.pk}')
            return None

        # Update token in DB
        token.token = new_access_token
        token.expires_at = timezone.now() + timedelta(seconds=expires_in)

        # Microsoft may return a new refresh token — update if so
        new_refresh_token = data.get('refresh_token')
        if new_refresh_token:
            token.token_secret = new_refresh_token

        token.save()

        logger.info(
            f'Refreshed Microsoft token for user {user.pk}, '
            f'new expiry: {token.expires_at.isoformat()}'
        )
        return new_access_token

    except requests.RequestException as e:
        logger.error(f'Microsoft token refresh request failed for user {user.pk}: {e}')
        return None


def get_valid_token(user, provider):
    """
    Convenience function: return a valid (refreshed if needed) access token
    string for the given provider ('google' or 'microsoft').
    Returns None if no token exists or refresh fails.
    """
    if provider == 'google':
        return refresh_google_token(user)
    elif provider == 'microsoft':
        return refresh_microsoft_token(user)
    else:
        logger.error(f'Unknown provider: {provider}')
        return None
