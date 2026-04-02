import logging
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    EvolizConnection,
    EvolizInvoice,
    EvolizPayment,
    EvolizPurchase,
)

logger = logging.getLogger(__name__)

EVOLIZ_LOGIN_URL = 'https://www.evoliz.io/api/login'
EVOLIZ_API_BASE = 'https://www.evoliz.io/api/v1'


class EvolizClient:
    """Thin wrapper around the Evoliz REST API using httpx."""

    def __init__(self, public_key: str, secret_key: str, company_id: str):
        self.public_key = public_key
        self.secret_key = secret_key
        self.company_id = company_id
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self.client = httpx.Client(
            base_url=f'{EVOLIZ_API_BASE}/companies/{company_id}',
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _get_token(self) -> str:
        """Authenticate and cache token. Re-authenticate when expired (20min TTL)."""
        now = datetime.now(dt_timezone.utc)
        if self._token and self._token_expires_at and now < self._token_expires_at:
            return self._token

        resp = httpx.post(
            EVOLIZ_LOGIN_URL,
            json={'public_key': self.public_key, 'secret_key': self.secret_key},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data['access_token']
        # Parse expires_at or fall back to 19min from now
        expires_at_str = data.get('expires_at')
        if expires_at_str:
            self._token_expires_at = datetime.fromisoformat(expires_at_str)
            if self._token_expires_at.tzinfo is None:
                self._token_expires_at = self._token_expires_at.replace(tzinfo=dt_timezone.utc)
        else:
            from datetime import timedelta
            self._token_expires_at = now + timedelta(minutes=19)

        return self._token

    def _request(self, method: str, endpoint: str, **kwargs) -> httpx.Response:
        """Make an authenticated request, refreshing token if needed."""
        token = self._get_token()
        self.client.headers['Authorization'] = f'Bearer {token}'
        resp = self.client.request(method, endpoint, **kwargs)
        resp.raise_for_status()
        return resp

    def _paginate(self, endpoint: str) -> list[dict]:
        """Handle Evoliz page-based pagination (page/per_page)."""
        results = []
        page = 1
        per_page = 100

        while True:
            resp = self._request('GET', endpoint, params={'page': page, 'per_page': per_page})
            data = resp.json()

            # Items can be in "data" key or at top level as list
            items = data.get('data', data) if isinstance(data, dict) else data
            if isinstance(items, list):
                results.extend(items)
            elif isinstance(items, dict):
                # Single item response
                results.append(items)
                break

            # Check pagination meta
            meta = data.get('meta', {}) if isinstance(data, dict) else {}
            current_page = meta.get('current_page', page)
            last_page = meta.get('last_page', page)

            if current_page >= last_page:
                break
            page += 1

        return results

    def list_invoices(self) -> list[dict]:
        return self._paginate('/invoices')

    def list_buys(self) -> list[dict]:
        return self._paginate('/buys')

    def list_payments(self) -> list[dict]:
        return self._paginate('/payments')


def _parse_date(value: str | None):
    """Parse date string (YYYY-MM-DD) from Evoliz."""
    if not value:
        return None
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def _dec(value) -> Decimal:
    """Safely convert to Decimal."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value))


def sync_evoliz_data(user) -> dict:
    """Sync all Evoliz data for a user. Returns stats dict."""
    try:
        connection = user.evoliz_connection
    except EvolizConnection.DoesNotExist:
        raise ValueError('No Evoliz connection found for this user')

    if not connection.is_active:
        raise ValueError('Evoliz connection is inactive')

    client = EvolizClient(connection.public_key, connection.secret_key, connection.company_id)
    stats = {'invoices': 0, 'purchases': 0, 'payments': 0}

    try:
        # Sync invoices
        try:
            stats['invoices'] = _sync_invoices(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Evoliz invoices for %s', user.email)
            stats['invoices_error'] = 'Failed to sync invoices'

        # Sync purchases
        try:
            stats['purchases'] = _sync_purchases(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Evoliz purchases for %s', user.email)
            stats['purchases_error'] = 'Failed to sync purchases'

        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Evoliz payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Evoliz sync for %s: %d invoices, %d purchases, %d payments',
        user.email, stats['invoices'], stats['purchases'], stats['payments'],
    )
    return stats


def _sync_invoices(client: EvolizClient, user, connection: EvolizConnection) -> int:
    """Sync invoices from Evoliz. Returns count."""
    raw_invoices = client.list_invoices()
    count = 0

    for inv in raw_invoices:
        # Client info
        client_obj = inv.get('client', {}) or {}

        EvolizInvoice.objects.update_or_create(
            evoliz_id=inv['invoiceid'],
            defaults={
                'user': user,
                'connection': connection,
                'document_number': inv.get('document_number', ''),
                'typedoc': inv.get('typedoc', ''),
                'status': inv.get('status', ''),
                'documentdate': _parse_date(inv.get('documentdate')),
                'duedate': _parse_date(inv.get('duedate')),
                'object_label': inv.get('object', '') or '',
                'client_name': client_obj.get('name', '') or '',
                'client_id_evoliz': client_obj.get('clientid') or None,
                'total_vat_exclude': _dec(inv.get('total_vat_exclude')),
                'total_vat': _dec(inv.get('total_vat')),
                'total_vat_include': _dec(inv.get('total_vat_include')),
                'total_paid': _dec(inv.get('total_paid', 0)),
                'net_to_pay': _dec(inv.get('net_to_pay', 0)),
                'currency': inv.get('currency', 'EUR') or 'EUR',
                'items': inv.get('items', []),
                'raw_data': inv,
            },
        )
        count += 1

    return count


def _sync_purchases(client: EvolizClient, user, connection: EvolizConnection) -> int:
    """Sync purchases (buys) from Evoliz. Returns count."""
    raw_buys = client.list_buys()
    count = 0

    for buy in raw_buys:
        supplier_obj = buy.get('supplier', {}) or {}

        EvolizPurchase.objects.update_or_create(
            evoliz_id=buy['buyid'],
            defaults={
                'user': user,
                'connection': connection,
                'document_number': buy.get('document_number', ''),
                'status': buy.get('status', ''),
                'documentdate': _parse_date(buy.get('documentdate')),
                'duedate': _parse_date(buy.get('duedate')),
                'supplier_name': supplier_obj.get('name', '') or '',
                'supplier_id_evoliz': supplier_obj.get('supplierid') or None,
                'total_vat_exclude': _dec(buy.get('total_vat_exclude')),
                'total_vat': _dec(buy.get('total_vat')),
                'total_vat_include': _dec(buy.get('total_vat_include')),
                'total_paid': _dec(buy.get('total_paid', 0)),
                'net_to_pay': _dec(buy.get('net_to_pay', 0)),
                'currency': buy.get('currency', 'EUR') or 'EUR',
                'items': buy.get('items', []),
                'raw_data': buy,
            },
        )
        count += 1

    return count


def _sync_payments(client: EvolizClient, user, connection: EvolizConnection) -> int:
    """Sync payments from Evoliz. Returns count."""
    raw_payments = client.list_payments()
    count = 0

    for p in raw_payments:
        EvolizPayment.objects.update_or_create(
            evoliz_id=p['paymentid'],
            defaults={
                'user': user,
                'connection': connection,
                'paydate': _parse_date(p.get('paydate')),
                'amount': _dec(p.get('amount')),
                'label': p.get('label', '') or '',
                'client_name': p.get('client_name', '') or '',
                'invoice_number': p.get('invoice_number', '') or '',
                'invoice_id_evoliz': p.get('invoiceid') or None,
                'paytype_label': p.get('paytype_label', '') or '',
                'currency': p.get('currency', 'EUR') or 'EUR',
                'raw_data': p,
            },
        )
        count += 1

    return count
