import logging
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    VosFacturesClient as VosFacturesClientModel,
    VosFacturesConnection,
    VosFacturesInvoice,
    VosFacturesPayment,
)

logger = logging.getLogger(__name__)


class VosFacturesClient:
    """Thin wrapper around the VosFactures REST API using httpx."""

    def __init__(self, api_token: str, account_prefix: str):
        self.api_token = api_token
        self.client = httpx.Client(
            base_url=f'https://{account_prefix}.vosfactures.fr',
            headers={
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _paginate(self, endpoint: str, params: dict | None = None) -> list[dict]:
        """Handle VosFactures page-based pagination.

        Page 1, 2, 3... until an empty array is returned.
        """
        results = []
        page = 1
        base_params = dict(params) if params else {}

        while True:
            request_params = {
                **base_params,
                'api_token': self.api_token,
                'page': page,
                'per_page': 100,
            }
            resp = self.client.get(endpoint, params=request_params)
            resp.raise_for_status()
            data = resp.json()

            if not data:
                break

            results.extend(data)
            page += 1

        return results

    def list_invoices(self, income: int = 1) -> list[dict]:
        """List invoices. income=1 for sales, income=0 for expenses."""
        return self._paginate('/invoices.json', params={'income': income})

    def list_payments(self) -> list[dict]:
        return self._paginate('/banking/payments.json')

    def list_clients(self) -> list[dict]:
        return self._paginate('/clients.json')


def _parse_date(value: str | None):
    """Parse date string (YYYY-MM-DD) from VosFactures. Returns None if empty."""
    if not value:
        return None
    try:
        from datetime import date
        return date.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def _parse_decimal(value) -> Decimal:
    """Parse decimal value from VosFactures. Amounts are decimal strings."""
    if value is None:
        return Decimal('0')
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal('0')


def sync_vosfactures_data(user) -> dict:
    """Sync all VosFactures data for a user. Returns stats dict."""
    try:
        connection = user.vosfactures_connection
    except VosFacturesConnection.DoesNotExist:
        raise ValueError('No VosFactures connection found for this user')

    if not connection.is_active:
        raise ValueError('VosFactures connection is inactive')

    client = VosFacturesClient(connection.api_token, connection.account_prefix)
    stats = {'invoices_sales': 0, 'invoices_expenses': 0, 'payments': 0, 'clients': 0}

    try:
        # Sync invoices (sales)
        try:
            stats['invoices_sales'] = _sync_invoices(client, user, connection, income=1)
        except Exception:
            logger.exception('Failed to sync VosFactures sales invoices for %s', user.email)
            stats['invoices_sales_error'] = 'Failed to sync sales invoices'

        # Sync invoices (expenses)
        try:
            stats['invoices_expenses'] = _sync_invoices(client, user, connection, income=0)
        except Exception:
            logger.exception('Failed to sync VosFactures expense invoices for %s', user.email)
            stats['invoices_expenses_error'] = 'Failed to sync expense invoices'

        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync VosFactures payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Sync clients
        try:
            stats['clients'] = _sync_clients(client, user, connection)
        except Exception:
            logger.exception('Failed to sync VosFactures clients for %s', user.email)
            stats['clients_error'] = 'Failed to sync clients'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'VosFactures sync for %s: %d sales invoices, %d expense invoices, %d payments, %d clients',
        user.email, stats['invoices_sales'], stats['invoices_expenses'],
        stats['payments'], stats['clients'],
    )
    return stats


def _sync_invoices(client: VosFacturesClient, user, connection: VosFacturesConnection, income: int = 1) -> int:
    """Sync invoices from VosFactures. Returns count of new/updated invoices."""
    raw_invoices = client.list_invoices(income=income)
    count = 0

    for inv in raw_invoices:
        VosFacturesInvoice.objects.update_or_create(
            vosfactures_id=inv['id'],
            defaults={
                'user': user,
                'connection': connection,
                'number': inv.get('number', '') or '',
                'kind': inv.get('kind', '') or '',
                'status': inv.get('status', '') or '',
                'issue_date': _parse_date(inv.get('issue_date')),
                'sell_date': inv.get('sell_date', '') or '',
                'payment_to': _parse_date(inv.get('payment_to')),
                'paid_date': _parse_date(inv.get('paid_date')),
                'price_net': _parse_decimal(inv.get('price_net')),
                'price_gross': _parse_decimal(inv.get('price_gross')),
                'price_tax': _parse_decimal(inv.get('price_tax')) if inv.get('price_tax') is not None else None,
                'paid': _parse_decimal(inv.get('paid', 0)),
                'currency': inv.get('currency', 'EUR') or 'EUR',
                'income': bool(income),
                'buyer_name': inv.get('buyer_name', '') or '',
                'buyer_tax_no': inv.get('buyer_tax_no', '') or '',
                'client_id_vf': inv.get('client_id'),
                'seller_name': inv.get('seller_name', '') or '',
                'payment_type': inv.get('payment_type', '') or '',
                'positions': inv.get('positions', []) or [],
                'raw_data': inv,
            },
        )
        count += 1

    return count


def _sync_payments(client: VosFacturesClient, user, connection: VosFacturesConnection) -> int:
    """Sync payments from VosFactures."""
    raw_payments = client.list_payments()
    count = 0

    for p in raw_payments:
        VosFacturesPayment.objects.update_or_create(
            vosfactures_id=p['id'],
            defaults={
                'user': user,
                'connection': connection,
                'price': _parse_decimal(p.get('price')),
                'paid_date': _parse_date(p.get('paid_date')),
                'currency': p.get('currency', 'EUR') or 'EUR',
                'invoice_id_vf': p.get('invoice_id'),
                'invoice_name': p.get('invoice_name', '') or '',
                'provider': p.get('provider', '') or '',
                'description': p.get('description', '') or '',
                'raw_data': p,
            },
        )
        count += 1

    return count


def _sync_clients(client: VosFacturesClient, user, connection: VosFacturesConnection) -> int:
    """Sync clients from VosFactures."""
    raw_clients = client.list_clients()
    count = 0

    for c in raw_clients:
        VosFacturesClientModel.objects.update_or_create(
            vosfactures_id=c['id'],
            defaults={
                'user': user,
                'connection': connection,
                'name': c.get('name', '') or '',
                'tax_no': c.get('tax_no', '') or '',
                'email': c.get('email', '') or '',
                'phone': c.get('phone', '') or '',
                'city': c.get('city', '') or '',
                'street': c.get('street', '') or '',
                'post_code': c.get('post_code', '') or '',
                'country': c.get('country', '') or '',
                'raw_data': c,
            },
        )
        count += 1

    return count
