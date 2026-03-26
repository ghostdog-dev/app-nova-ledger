import logging
from datetime import datetime
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import (
    MollieConnection,
    MollieInvoice,
    MolliePayment,
    MollieRefund,
    MollieSettlement,
)

logger = logging.getLogger(__name__)

MOLLIE_API_BASE = 'https://api.mollie.com/v2'


class MollieClient:
    """Thin wrapper around the Mollie REST API using httpx."""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.client = httpx.Client(
            base_url=MOLLIE_API_BASE,
            headers={
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def get_organization(self) -> dict:
        """GET /v2/organizations/me -- verify token and get org info."""
        resp = self.client.get('/organizations/me')
        resp.raise_for_status()
        return resp.json()

    def _paginate(self, endpoint: str, resource_key: str, params: dict | None = None) -> list[dict]:
        """Handle Mollie cursor-based pagination.

        Mollie uses _links.next.href for pagination.
        """
        results = []
        url = endpoint
        is_absolute = False

        while url:
            if is_absolute:
                resp = httpx.get(
                    url,
                    headers={'Authorization': f'Bearer {self.access_token}'},
                    timeout=30.0,
                )
            else:
                resp = self.client.get(url, params=params)
                params = None  # only on first request

            resp.raise_for_status()
            data = resp.json()

            embedded = data.get('_embedded', {})
            items = embedded.get(resource_key, [])
            results.extend(items)

            # Follow cursor-based pagination
            next_link = data.get('_links', {}).get('next')
            if next_link and next_link.get('href'):
                url = next_link['href']
                is_absolute = True
            else:
                url = None

        return results

    def list_payments(self, limit: int = 250) -> list[dict]:
        return self._paginate('/payments', 'payments', params={'limit': limit})

    def list_refunds(self, limit: int = 250) -> list[dict]:
        return self._paginate('/refunds', 'refunds', params={'limit': limit})

    def list_settlements(self, limit: int = 250) -> list[dict]:
        return self._paginate('/settlements', 'settlements', params={'limit': limit})

    def list_invoices(self, limit: int = 250) -> list[dict]:
        return self._paginate('/invoices', 'invoices', params={'limit': limit})


def _parse_amount(amount_obj: dict | None) -> tuple[Decimal | None, str]:
    """Parse Mollie amount object {"value": "10.00", "currency": "EUR"}."""
    if not amount_obj:
        return None, ''
    return Decimal(amount_obj['value']), amount_obj.get('currency', '')


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from Mollie."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def sync_mollie_data(user) -> dict:
    """Sync all Mollie data for a user. Returns stats dict."""
    try:
        connection = user.mollie_connection
    except MollieConnection.DoesNotExist:
        raise ValueError('No Mollie connection found for this user')

    if not connection.is_active:
        raise ValueError('Mollie connection is inactive')

    # API keys don't expire -- use directly
    client = MollieClient(connection.api_key)
    stats = {'payments': 0, 'refunds': 0, 'settlements': 0, 'invoices': 0}

    try:
        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Mollie payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Sync refunds
        try:
            stats['refunds'] = _sync_refunds(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Mollie refunds for %s', user.email)
            stats['refunds_error'] = 'Failed to sync refunds'

        # Sync settlements
        try:
            stats['settlements'] = _sync_settlements(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Mollie settlements for %s', user.email)
            stats['settlements_error'] = 'Failed to sync settlements'

        # Sync invoices
        try:
            stats['invoices'] = _sync_invoices(client, user, connection)
        except Exception:
            logger.exception('Failed to sync Mollie invoices for %s', user.email)
            stats['invoices_error'] = 'Failed to sync invoices'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Mollie sync for %s: %d payments, %d refunds, %d settlements, %d invoices',
        user.email, stats['payments'], stats['refunds'],
        stats['settlements'], stats['invoices'],
    )
    return stats


def _sync_payments(client: MollieClient, user, connection: MollieConnection) -> int:
    """Sync payments from Mollie. Returns count of new/updated payments."""
    raw_payments = client.list_payments()
    count = 0

    for p in raw_payments:
        amount, currency = _parse_amount(p.get('amount'))
        settle_amount, settle_currency = _parse_amount(p.get('settlementAmount'))

        # Extract payment method details
        details = p.get('details', {}) or {}

        _, updated = MolliePayment.objects.update_or_create(
            mollie_id=p['id'],
            defaults={
                'user': user,
                'connection': connection,
                'amount': amount,
                'currency': currency,
                'settlement_amount': settle_amount,
                'settlement_currency': settle_currency or '',
                'status': p.get('status', ''),
                'description': p.get('description', ''),
                'method': p.get('method') or '',
                # Card details
                'card_holder': details.get('cardHolder', ''),
                'card_number': details.get('cardNumber', ''),
                'card_brand': details.get('cardLabel', ''),
                'card_country': details.get('cardCountryCode', ''),
                'card_security': details.get('cardSecurity', ''),
                # iDEAL details
                'ideal_consumer_name': details.get('consumerName', ''),
                'ideal_consumer_account': details.get('consumerAccount', ''),
                'ideal_consumer_bic': details.get('consumerBic', ''),
                # SEPA
                'bank_transfer_reference': details.get('transferReference', ''),
                # URLs
                'redirect_url': p.get('redirectUrl', '') or '',
                'webhook_url': p.get('webhookUrl', '') or '',
                # Order & metadata
                'order_id': p.get('orderId', '') or '',
                'metadata': p.get('metadata') or {},
                # Locale
                'locale': p.get('locale', '') or '',
                'country_code': p.get('countryCode', '') or '',
                # Dates
                'created_at_mollie': _parse_dt(p['createdAt']),
                'paid_at': _parse_dt(p.get('paidAt')),
                'expires_at': _parse_dt(p.get('expiresAt')),
                'canceled_at': _parse_dt(p.get('canceledAt')),
                'failed_at': _parse_dt(p.get('failedAt')),
                'raw_data': p,
            },
        )
        count += 1

    return count


def _sync_refunds(client: MollieClient, user, connection: MollieConnection) -> int:
    """Sync refunds from Mollie."""
    raw_refunds = client.list_refunds()
    count = 0

    for r in raw_refunds:
        amount, currency = _parse_amount(r.get('amount'))
        settle_amount, _ = _parse_amount(r.get('settlementAmount'))

        MollieRefund.objects.update_or_create(
            mollie_id=r['id'],
            defaults={
                'user': user,
                'connection': connection,
                'payment_id': r.get('paymentId', ''),
                'amount': amount,
                'currency': currency,
                'settlement_amount': settle_amount,
                'status': r.get('status', ''),
                'description': r.get('description', ''),
                'created_at_mollie': _parse_dt(r['createdAt']),
                'raw_data': r,
            },
        )
        count += 1

    return count


def _sync_settlements(client: MollieClient, user, connection: MollieConnection) -> int:
    """Sync settlements from Mollie."""
    raw_settlements = client.list_settlements()
    count = 0

    for s in raw_settlements:
        amount, currency = _parse_amount(s.get('amount'))

        MollieSettlement.objects.update_or_create(
            mollie_id=s['id'],
            defaults={
                'user': user,
                'connection': connection,
                'amount': amount,
                'currency': currency,
                'status': s.get('status', ''),
                'periods': s.get('periods', {}),
                'settled_at': _parse_dt(s.get('settledAt')),
                'created_at_mollie': _parse_dt(s['createdAt']),
                'raw_data': s,
            },
        )
        count += 1

    return count


def _sync_invoices(client: MollieClient, user, connection: MollieConnection) -> int:
    """Sync invoices from Mollie."""
    raw_invoices = client.list_invoices()
    count = 0

    for inv in raw_invoices:
        gross_amount, currency = _parse_amount(inv.get('grossAmount'))
        net_amount, _ = _parse_amount(inv.get('netAmount'))
        vat_amount, _ = _parse_amount(inv.get('vatAmount'))

        MollieInvoice.objects.update_or_create(
            mollie_id=inv['id'],
            defaults={
                'user': user,
                'connection': connection,
                'reference': inv.get('reference', ''),
                'vat_number': inv.get('vatNumber', ''),
                'gross_amount': gross_amount,
                'net_amount': net_amount,
                'vat_amount': vat_amount,
                'currency': currency,
                'status': inv.get('status', ''),
                'issued_at': _parse_dt(inv.get('issuedAt')),
                'due_at': _parse_dt(inv.get('dueAt')),
                'paid_at': _parse_dt(inv.get('paidAt')),
                'pdf_url': inv.get('_links', {}).get('pdf', {}).get('href', ''),
                'lines': inv.get('lines', []),
                'raw_data': inv,
            },
        )
        count += 1

    return count
