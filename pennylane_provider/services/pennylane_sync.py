import logging
import time
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    PennylaneConnection,
    PennylaneCustomerInvoice,
    PennylaneSupplierInvoice,
    PennylaneTransaction,
)

logger = logging.getLogger(__name__)

PENNYLANE_API_BASE = 'https://app.pennylane.com/api/external/v2'


class PennylaneClient:
    """Thin wrapper around the Pennylane REST API v2 using httpx."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.Client(
            base_url=PENNYLANE_API_BASE,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _handle_rate_limit(self, response: httpx.Response):
        """Handle 429 rate limit by sleeping for Retry-After duration."""
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', '5')
            try:
                wait = int(retry_after)
            except (ValueError, TypeError):
                wait = 5
            logger.warning('Pennylane rate limited, sleeping %d seconds', wait)
            time.sleep(wait)
            return True
        return False

    def _paginate(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Handle Pennylane cursor-based pagination.

        Pennylane uses cursor + limit params. Response has has_more (bool) + next_cursor (string or null).
        """
        results = []
        params = dict(params or {})
        params.setdefault('limit', 100)

        while True:
            resp = self.client.get(endpoint, params=params)

            # Handle rate limiting
            if self._handle_rate_limit(resp):
                continue

            resp.raise_for_status()
            data = resp.json()

            items = data.get('items', data.get('data', []))
            results.extend(items)

            # Follow cursor-based pagination
            has_more = data.get('has_more', False)
            next_cursor = data.get('next_cursor')
            if has_more and next_cursor:
                params['cursor'] = next_cursor
            else:
                break

        return results

    def list_customer_invoices(self) -> list[dict]:
        return self._paginate('/customer_invoices')

    def list_supplier_invoices(self) -> list[dict]:
        return self._paginate('/supplier_invoices')

    def list_transactions(self) -> list[dict]:
        return self._paginate('/transactions')


def _parse_decimal(value) -> Decimal:
    """Parse a decimal string from Pennylane. Amounts are decimal strings (not cents)."""
    if value is None:
        return Decimal('0')
    return Decimal(str(value))


def _parse_decimal_nullable(value) -> Decimal | None:
    """Parse a nullable decimal string from Pennylane."""
    if value is None:
        return None
    return Decimal(str(value))


def sync_pennylane_data(user) -> dict:
    """Sync all Pennylane data for a user. Returns stats dict."""
    try:
        connection = user.pennylane_connection
    except PennylaneConnection.DoesNotExist:
        raise ValueError('No Pennylane connection found for this user')

    if not connection.is_active:
        raise ValueError('Pennylane connection is inactive')

    client = PennylaneClient(connection.access_token)
    stats = {'customer_invoices': 0, 'supplier_invoices': 0, 'transactions': 0}

    try:
        # Sync customer invoices
        try:
            stats['customer_invoices'] = _sync_customer_invoices(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Pennylane customer invoices for %s', user.email)
            stats['customer_invoices_error'] = 'Failed to sync customer invoices'

        # Sync supplier invoices
        try:
            stats['supplier_invoices'] = _sync_supplier_invoices(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Pennylane supplier invoices for %s', user.email)
            stats['supplier_invoices_error'] = 'Failed to sync supplier invoices'

        # Sync transactions
        try:
            stats['transactions'] = _sync_transactions(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Pennylane transactions for %s', user.email)
            stats['transactions_error'] = 'Failed to sync transactions'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Pennylane sync for %s: %d customer invoices, %d supplier invoices, %d transactions',
        user.email, stats['customer_invoices'], stats['supplier_invoices'],
        stats['transactions'],
    )
    return stats


def _sync_customer_invoices(client: PennylaneClient, user, connection: PennylaneConnection) -> int:
    """Sync customer invoices from Pennylane. Returns count of new/updated invoices."""
    raw_invoices = client.list_customer_invoices()
    count = 0

    for inv in raw_invoices:
        PennylaneCustomerInvoice.objects.update_or_create(
            pennylane_id=str(inv['id']),
            defaults={
                'user': user,
                'connection': connection,
                'invoice_number': inv.get('invoice_number', '') or '',
                'status': inv.get('status', ''),
                'date': inv.get('date'),
                'deadline': inv.get('deadline'),
                'customer_name': inv.get('customer_name', '') or inv.get('customer', {}).get('name', '') or '',
                'customer_id_pennylane': str(inv.get('customer_id', '') or inv.get('customer', {}).get('id', '') or ''),
                'amount': _parse_decimal(inv.get('amount')),
                'currency': inv.get('currency', 'EUR') or 'EUR',
                'tax': _parse_decimal_nullable(inv.get('tax')),
                'total': _parse_decimal(inv.get('total')),
                'paid_amount': _parse_decimal(inv.get('paid_amount', 0)),
                'remaining_amount': _parse_decimal(inv.get('remaining_amount', 0)),
                'line_items': inv.get('line_items', []) or [],
                'raw_data': inv,
            },
        )
        count += 1

    return count


def _sync_supplier_invoices(client: PennylaneClient, user, connection: PennylaneConnection) -> int:
    """Sync supplier invoices from Pennylane. Returns count of new/updated invoices."""
    raw_invoices = client.list_supplier_invoices()
    count = 0

    for inv in raw_invoices:
        PennylaneSupplierInvoice.objects.update_or_create(
            pennylane_id=str(inv['id']),
            defaults={
                'user': user,
                'connection': connection,
                'invoice_number': inv.get('invoice_number', '') or '',
                'status': inv.get('status', ''),
                'date': inv.get('date'),
                'deadline': inv.get('deadline'),
                'supplier_name': inv.get('supplier_name', '') or inv.get('supplier', {}).get('name', '') or '',
                'supplier_id_pennylane': str(inv.get('supplier_id', '') or inv.get('supplier', {}).get('id', '') or ''),
                'amount': _parse_decimal(inv.get('amount')),
                'currency': inv.get('currency', 'EUR') or 'EUR',
                'tax': _parse_decimal_nullable(inv.get('tax')),
                'total': _parse_decimal(inv.get('total')),
                'paid_amount': _parse_decimal(inv.get('paid_amount', 0)),
                'remaining_amount': _parse_decimal(inv.get('remaining_amount', 0)),
                'line_items': inv.get('line_items', []) or [],
                'raw_data': inv,
            },
        )
        count += 1

    return count


def _sync_transactions(client: PennylaneClient, user, connection: PennylaneConnection) -> int:
    """Sync transactions from Pennylane. Returns count of new/updated transactions."""
    raw_transactions = client.list_transactions()
    count = 0

    for t in raw_transactions:
        PennylaneTransaction.objects.update_or_create(
            pennylane_id=str(t['id']),
            defaults={
                'user': user,
                'connection': connection,
                'date': t['date'],
                'amount': _parse_decimal(t.get('amount')),
                'currency': t.get('currency', 'EUR') or 'EUR',
                'label': t.get('label', '') or '',
                'bank_account_name': t.get('bank_account_name', '') or t.get('bank_account', {}).get('name', '') or '',
                'category': t.get('category', '') or '',
                'raw_data': t,
            },
        )
        count += 1

    return count
