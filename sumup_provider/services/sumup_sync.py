import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    SumUpConnection,
    SumUpPayout,
    SumUpTransaction,
)

logger = logging.getLogger(__name__)

SUMUP_API_BASE = 'https://api.sumup.com'


class SumUpClient:
    """Thin wrapper around the SumUp REST API using httpx."""

    def __init__(self, api_key: str, merchant_code: str):
        self.merchant_code = merchant_code
        self.client = httpx.Client(
            base_url=SUMUP_API_BASE,
            headers={
                'Authorization': f'Bearer {api_key}',
                'Accept': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def get_merchant_profile(self) -> dict:
        """GET /v0.1/me/merchant-profile -- verify key and get merchant info."""
        resp = self.client.get('/v0.1/me/merchant-profile')
        resp.raise_for_status()
        return resp.json()

    def list_transactions(self, oldest_time: str | None = None, limit: int = 50) -> list[dict]:
        """List transactions with cursor-based pagination via links[].rel="next"."""
        all_items = []
        params = {'limit': limit, 'order': 'descending'}
        if oldest_time:
            params['oldest_time'] = oldest_time

        url = f'/v2.1/merchants/{self.merchant_code}/transactions/history'
        while url:
            resp = self.client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            items = data.get('items', [])
            all_items.extend(items)

            # Find next cursor
            params = None  # only first request uses params
            next_link = next((l for l in data.get('links', []) if l.get('rel') == 'next'), None)
            if next_link and items:
                # href contains query string to append
                url = f'/v2.1/merchants/{self.merchant_code}/transactions/history?{next_link["href"]}'
            else:
                url = None

        return all_items

    def list_payouts(self, start_date: str, end_date: str) -> list[dict]:
        """List payouts for date range. Returns flat JSON array."""
        resp = self.client.get(
            f'/v1.0/merchants/{self.merchant_code}/payouts',
            params={'start_date': start_date, 'end_date': end_date, 'format': 'json'},
        )
        resp.raise_for_status()
        return resp.json()  # flat array


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from SumUp."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_date(value: str | None):
    """Parse YYYY-MM-DD date string from SumUp."""
    if not value:
        return None
    return datetime.strptime(value, '%Y-%m-%d').date()


def sync_sumup_data(user, days_back: int = 90) -> dict:
    """Sync all SumUp data for a user. Returns stats dict."""
    try:
        connection = user.sumup_connection
    except SumUpConnection.DoesNotExist:
        raise ValueError('No SumUp connection found for this user')

    if not connection.is_active:
        raise ValueError('SumUp connection is inactive')

    client = SumUpClient(connection.api_key, connection.merchant_code)
    stats = {'transactions': 0, 'payouts': 0}

    oldest_time = (timezone.now() - timedelta(days=days_back)).isoformat()
    end_date = timezone.now().strftime('%Y-%m-%d')
    start_date = (timezone.now() - timedelta(days=days_back)).strftime('%Y-%m-%d')

    try:
        # Sync transactions
        try:
            stats['transactions'] = _sync_transactions(client, user, connection, oldest_time)
        except Exception:
            logger.exception('Failed to sync SumUp transactions for %s', user.email)
            stats['transactions_error'] = 'Failed to sync transactions'

        # Sync payouts
        try:
            stats['payouts'] = _sync_payouts(client, user, connection, start_date, end_date)
        except Exception:
            logger.exception('Failed to sync SumUp payouts for %s', user.email)
            stats['payouts_error'] = 'Failed to sync payouts'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'SumUp sync for %s: %d transactions, %d payouts',
        user.email, stats['transactions'], stats['payouts'],
    )
    return stats


def _sync_transactions(client: SumUpClient, user, connection: SumUpConnection, oldest_time: str) -> int:
    """Sync transactions from SumUp. Returns count of new/updated transactions."""
    raw_transactions = client.list_transactions(oldest_time=oldest_time)
    count = 0

    for t in raw_transactions:
        card = t.get('card') or {}

        SumUpTransaction.objects.update_or_create(
            sumup_id=t['id'],
            defaults={
                'user': user,
                'connection': connection,
                'transaction_code': t.get('transaction_code', ''),
                'amount': Decimal(str(t['amount'])),
                'vat_amount': Decimal(str(t['vat_amount'])) if t.get('vat_amount') is not None else None,
                'tip_amount': Decimal(str(t['tip_amount'])) if t.get('tip_amount') is not None else None,
                'fee_amount': Decimal(str(t['fee_amount'])) if t.get('fee_amount') is not None else None,
                'refunded_amount': Decimal(str(t['refunded_amount'])) if t.get('refunded_amount') is not None else None,
                'currency': t.get('currency', ''),
                'timestamp': _parse_dt(t['timestamp']),
                'status': t.get('status', ''),
                'type': t.get('type', ''),
                'payment_type': t.get('payment_type', ''),
                'entry_mode': t.get('entry_mode', ''),
                'card_type': card.get('type', ''),
                'card_last4': card.get('last_4_digits', ''),
                'product_summary': t.get('product_summary', ''),
                'installments_count': t.get('installments_count', 1),
                'payout_date': _parse_date(t.get('payout_date')),
                'payout_type': t.get('payout_type', ''),
                'auth_code': t.get('auth_code', ''),
                'internal_id': t.get('internal_id'),
                'products': t.get('products', []),
                'vat_rates': t.get('vat_rates', []),
                'metadata': {},
                'raw_data': t,
            },
        )
        count += 1

    return count


def _sync_payouts(client: SumUpClient, user, connection: SumUpConnection, start_date: str, end_date: str) -> int:
    """Sync payouts from SumUp. Returns count of new/updated payouts."""
    raw_payouts = client.list_payouts(start_date, end_date)
    count = 0

    for p in raw_payouts:
        SumUpPayout.objects.update_or_create(
            sumup_id=p['id'],
            defaults={
                'user': user,
                'connection': connection,
                'amount': Decimal(str(p['amount'])),
                'currency': p.get('currency', ''),
                'date': _parse_date(p.get('date')),
                'fee': Decimal(str(p.get('fee', 0))),
                'status': p.get('status', ''),
                'type': p.get('type', ''),
                'reference': p.get('reference', ''),
                'transaction_code': p.get('transaction_code', ''),
                'raw_data': p,
            },
        )
        count += 1

    return count
