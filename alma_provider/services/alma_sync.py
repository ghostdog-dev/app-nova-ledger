import logging
from datetime import datetime, timezone

import httpx
from django.utils import timezone as dj_timezone

from ..models import AlmaConnection, AlmaPayment

logger = logging.getLogger(__name__)

ALMA_SANDBOX_BASE = 'https://api.sandbox.getalma.eu/v1'
ALMA_PRODUCTION_BASE = 'https://api.getalma.eu/v1'


class AlmaClient:
    """Thin wrapper around the Alma REST API using httpx."""

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.is_sandbox = api_key.startswith('sk_test_')
        base_url = ALMA_SANDBOX_BASE if self.is_sandbox else ALMA_PRODUCTION_BASE
        self.client = httpx.Client(
            base_url=base_url,
            headers={
                'Authorization': f'Alma-Auth {api_key}',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def list_all_payments(self, state: str | None = None) -> list[dict]:
        """List all payments with cursor-based pagination.

        Alma uses ?limit=100&starting_after={last_id} and has_more flag.
        """
        results = []
        params: dict = {'limit': 100}
        if state:
            params['state'] = state

        while True:
            resp = self.client.get('/payments', params=params)
            resp.raise_for_status()
            data = resp.json()

            items = data.get('data', [])
            results.extend(items)

            if not data.get('has_more', False) or not items:
                break

            # Set starting_after to last item's id for next page
            params['starting_after'] = items[-1]['id']

        return results

    def get_payment(self, payment_id: str) -> dict:
        """GET /v1/payments/{id}."""
        resp = self.client.get(f'/payments/{payment_id}')
        resp.raise_for_status()
        return resp.json()


def _parse_timestamp(ts) -> datetime | None:
    """Convert Unix timestamp (int/float) to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def sync_alma_data(user) -> dict:
    """Sync all Alma data for a user. Returns stats dict."""
    try:
        connection = user.alma_connection
    except AlmaConnection.DoesNotExist:
        raise ValueError('No Alma connection found for this user')

    if not connection.is_active:
        raise ValueError('Alma connection is inactive')

    client = AlmaClient(connection.api_key)
    stats = {'payments': 0}

    try:
        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Alma payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Update last_sync
        connection.last_sync = dj_timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info('Alma sync for %s: %d payments', user.email, stats['payments'])
    return stats


def _sync_payments(client: AlmaClient, user, connection: AlmaConnection) -> int:
    """Sync payments from Alma. Returns count of new/updated payments."""
    raw_payments = client.list_all_payments()
    count = 0

    for p in raw_payments:
        customer = p.get('customer', {}) or {}
        orders = p.get('orders', []) or []
        merchant_reference = orders[0].get('merchant_reference', '') if orders else ''

        AlmaPayment.objects.update_or_create(
            alma_id=p['id'],
            defaults={
                'user': user,
                'connection': connection,
                'state': p.get('state', ''),
                'processing_status': p.get('processing_status', '') or '',
                'purchase_amount': p.get('purchase_amount', 0),
                'customer_fee': p.get('customer_fee', 0) or 0,
                'installments_count': p.get('installments_count', 0),
                'kind': p.get('kind', '') or '',
                'customer_email': customer.get('email', '') or '',
                'customer_name': ' '.join(filter(None, [
                    customer.get('first_name', ''),
                    customer.get('last_name', ''),
                ])),
                'customer_phone': customer.get('phone', '') or '',
                'merchant_reference': merchant_reference or '',
                'payment_plan': p.get('payment_plan', []) or [],
                'refunds': p.get('refunds', []) or [],
                'amount_already_refunded': p.get('amount_already_refunded', 0) or 0,
                'is_completely_refunded': p.get('is_completely_refunded', False),
                'payout_status': p.get('payout_status', '') or '',
                'currency': p.get('currency', 'EUR') or 'EUR',
                'raw_data': p,
                'created_at_alma': _parse_timestamp(p.get('created')),
            },
        )
        count += 1

    return count
