import base64
import logging
import time
from datetime import date
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    FintectureConnection,
    FintecturePayment,
    FintectureSettlement,
)

logger = logging.getLogger(__name__)

FINTECTURE_SANDBOX_BASE = 'https://api-sandbox.fintecture.com'
FINTECTURE_PRODUCTION_BASE = 'https://api.fintecture.com'


class FintectureClient:
    """Thin wrapper around the Fintecture REST API using httpx.

    NOTE: HTTP Signature is skipped for now (sandbox doesn't require it).
    For production, HTTP Signature headers must be added to each request.
    See: https://docs.fintecture.com/docs/authentication#http-signature
    """

    def __init__(self, app_id: str, app_secret: str, is_sandbox: bool = True):
        self.app_id = app_id
        self.app_secret = app_secret
        self.is_sandbox = is_sandbox
        self._access_token = None
        self._token_expires_at = 0.0

        base_url = FINTECTURE_SANDBOX_BASE if is_sandbox else FINTECTURE_PRODUCTION_BASE
        self.client = httpx.Client(
            base_url=base_url,
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _get_access_token(self) -> str:
        """POST /oauth/accesstoken — request a new access token using client_credentials.

        Token expires in ~10min, no refresh token — request a new one each time.
        """
        if self._access_token and time.time() < self._token_expires_at:
            return self._access_token

        credentials = base64.b64encode(f'{self.app_id}:{self.app_secret}'.encode()).decode()
        resp = self.client.post(
            '/oauth/accesstoken',
            headers={
                'Authorization': f'Basic {credentials}',
                'Content-Type': 'application/x-www-form-urlencoded',
                'Accept': 'application/json',
            },
            content=f'grant_type=client_credentials&app_id={self.app_id}&scope=PIS',
        )
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data['access_token']
        # Expire 60s early to avoid edge cases
        self._token_expires_at = time.time() + data.get('expires_in', 599) - 60

        return self._access_token

    def _headers(self) -> dict:
        """Return Authorization Bearer + Accept headers."""
        token = self._get_access_token()
        return {
            'Authorization': f'Bearer {token}',
            'Accept': 'application/json',
        }

    def list_payments(self, page: int = 1, page_size: int = 100) -> list[dict]:
        """GET /pis/v2/payments with pagination. Returns all payments."""
        all_payments = []

        while True:
            resp = self.client.get(
                '/pis/v2/payments',
                headers=self._headers(),
                params={'page[number]': page, 'page[size]': page_size},
            )
            resp.raise_for_status()
            body = resp.json()

            data = body.get('data', [])
            all_payments.extend(data)

            meta = body.get('meta', {})
            total_pages = meta.get('totalPages', 1)

            if page >= total_pages:
                break
            page += 1

        return all_payments

    def list_settlements(self, page: int = 1, page_size: int = 100) -> list[dict]:
        """GET /pis/v2/settlements with pagination. Returns all settlements."""
        all_settlements = []

        while True:
            resp = self.client.get(
                '/pis/v2/settlements',
                headers=self._headers(),
                params={'page[number]': page, 'page[size]': page_size},
            )
            resp.raise_for_status()
            body = resp.json()

            data = body.get('data', [])
            all_settlements.extend(data)

            meta = body.get('meta', {})
            total_pages = meta.get('totalPages', 1)

            if page >= total_pages:
                break
            page += 1

        return all_settlements


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD date string from Fintecture."""
    if not value:
        return None
    return date.fromisoformat(value)


def sync_fintecture_data(user) -> dict:
    """Sync all Fintecture data for a user. Returns stats dict."""
    try:
        connection = user.fintecture_connection
    except FintectureConnection.DoesNotExist:
        raise ValueError('No Fintecture connection found for this user')

    if not connection.is_active:
        raise ValueError('Fintecture connection is inactive')

    client = FintectureClient(connection.app_id, connection.app_secret, is_sandbox=connection.is_sandbox)
    stats = {'payments': 0, 'settlements': 0}

    try:
        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Fintecture payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Sync settlements
        try:
            stats['settlements'] = _sync_settlements(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Fintecture settlements for %s', user.email)
            stats['settlements_error'] = 'Failed to sync settlements'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Fintecture sync for %s: %d payments, %d settlements',
        user.email, stats['payments'], stats['settlements'],
    )
    return stats


def _sync_payments(client: FintectureClient, user, connection: FintectureConnection) -> int:
    """Sync payments from Fintecture. Returns count of new/updated payments."""
    raw_payments = client.list_payments()
    count = 0

    for p in raw_payments:
        attrs = p.get('attributes', {})
        meta = p.get('meta', {})

        FintecturePayment.objects.update_or_create(
            session_id=meta.get('session_id', p['id']),
            defaults={
                'user': user,
                'connection': connection,
                'amount': Decimal(attrs.get('amount', '0')),
                'currency': attrs.get('currency', ''),
                'communication': attrs.get('communication', ''),
                'end_to_end_id': attrs.get('end_to_end_id', ''),
                'execution_date': _parse_date(attrs.get('execution_date')),
                'payment_scheme': attrs.get('payment_scheme', ''),
                'transfer_state': attrs.get('transfer_state', ''),
                'status': meta.get('status', ''),
                'session_type': meta.get('type', ''),
                'provider': meta.get('provider', ''),
                'customer_id': meta.get('customer_id', ''),
                'bank_account_id': attrs.get('bank_account_id', ''),
                'is_accepted': meta.get('is_accepted', False),
                'has_settlement_completed': meta.get('has_settlement_completed', False),
                'metadata': {},
                'raw_data': p,
            },
        )
        count += 1

    return count


def _sync_settlements(client: FintectureClient, user, connection: FintectureConnection) -> int:
    """Sync settlements from Fintecture."""
    raw_settlements = client.list_settlements()
    count = 0

    for s in raw_settlements:
        attrs = s.get('attributes', {})

        FintectureSettlement.objects.update_or_create(
            settlement_id=s['id'],
            defaults={
                'user': user,
                'connection': connection,
                'amount': Decimal(attrs.get('amount', '0')),
                'currency': attrs.get('currency', ''),
                'status': attrs.get('status', ''),
                'execution_date': _parse_date(attrs.get('execution_date')),
                'raw_data': s,
            },
        )
        count += 1

    return count
