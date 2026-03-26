import logging
import urllib.parse
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx

from ..models import PayPalConnection, PayPalDispute, PayPalInvoice, PayPalTransaction

logger = logging.getLogger(__name__)

SANDBOX_BASE = 'https://api-m.sandbox.paypal.com'
LIVE_BASE = 'https://api-m.paypal.com'


class PayPalClient:
    """PayPal REST API client using httpx."""

    def __init__(self, connection: PayPalConnection):
        self.connection = connection
        self.base_url = SANDBOX_BASE if connection.is_sandbox else LIVE_BASE
        self._access_token = None

    def _get_access_token(self) -> str:
        """Get OAuth2 access token using client credentials."""
        if self._access_token:
            return self._access_token

        resp = httpx.post(
            f'{self.base_url}/v1/oauth2/token',
            auth=(self.connection.client_id, self.connection.client_secret),
            data={'grant_type': 'client_credentials'},
            headers={'Accept': 'application/json'},
            timeout=30,
        )
        resp.raise_for_status()
        self._access_token = resp.json()['access_token']
        return self._access_token

    def _force_refresh_token(self) -> str:
        """Force a token refresh by clearing the cached token."""
        self._access_token = None
        return self._get_access_token()

    def _headers(self) -> dict:
        return {
            'Authorization': f'Bearer {self._get_access_token()}',
            'Content-Type': 'application/json',
        }

    def _make_request(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make an HTTP request with automatic 401 retry (token refresh)."""
        kwargs.setdefault('headers', self._headers())
        resp = getattr(httpx, method)(url, **kwargs)
        if resp.status_code == 401:
            logger.info('PayPal 401 received, refreshing access token and retrying')
            self._force_refresh_token()
            kwargs['headers'] = self._headers()
            resp = getattr(httpx, method)(url, **kwargs)
        resp.raise_for_status()
        return resp

    def verify_credentials(self) -> dict:
        """Verify client_id/client_secret by fetching a token and user info."""
        self._get_access_token()
        resp = self._make_request(
            'get',
            f'{self.base_url}/v1/identity/oauth2/userinfo?schema=paypalv1.1',
            timeout=30,
        )
        return resp.json()

    def fetch_transactions(self, start_date: datetime, end_date: datetime) -> list[dict]:
        """Fetch transactions from the reporting API. Handles pagination."""
        all_transactions = []
        page = 1
        page_size = 100

        while True:
            params = {
                'start_date': start_date.strftime('%Y-%m-%dT%H:%M:%S-0000'),
                'end_date': end_date.strftime('%Y-%m-%dT%H:%M:%S-0000'),
                'fields': 'all',
                'page_size': page_size,
                'page': page,
            }
            resp = self._make_request(
                'get',
                f'{self.base_url}/v1/reporting/transactions',
                params=params,
                timeout=60,
            )
            data = resp.json()

            transactions = data.get('transaction_details', [])
            all_transactions.extend(transactions)

            total_pages = data.get('total_pages', 1)
            logger.info('PayPal transactions page %d/%d, got %d', page, total_pages, len(transactions))

            if page >= total_pages:
                break
            page += 1

        return all_transactions

    def fetch_invoices(self) -> list[dict]:
        """Fetch invoices. Handles pagination."""
        all_invoices = []
        page = 1
        page_size = 100

        while True:
            body = {
                'page': page,
                'page_size': page_size,
                'total_required': True,
            }
            resp = self._make_request(
                'post',
                f'{self.base_url}/v2/invoicing/invoices?page={page}&page_size={page_size}&total_required=true',
                json=body,
                timeout=60,
            )
            data = resp.json()

            items = data.get('items', [])
            all_invoices.extend(items)

            total_pages = data.get('total_pages', 1)
            logger.info('PayPal invoices page %d/%d, got %d', page, total_pages, len(items))

            if page >= total_pages:
                break
            page += 1

        return all_invoices

    def fetch_disputes(self) -> list[dict]:
        """Fetch disputes. Handles pagination."""
        all_disputes = []
        start_time = (datetime.now(timezone.utc) - timedelta(days=180)).strftime('%Y-%m-%dT%H:%M:%S.000Z')
        next_page_token = None

        while True:
            params = {
                'start_time': start_time,
                'page_size': 50,
            }
            if next_page_token:
                params['next_page_token'] = next_page_token

            resp = self._make_request(
                'get',
                f'{self.base_url}/v1/customer/disputes',
                params=params,
                timeout=60,
            )
            data = resp.json()

            items = data.get('items', [])
            all_disputes.extend(items)

            # Check for next page
            links = data.get('links', [])
            next_link = next((l for l in links if l.get('rel') == 'next'), None)
            if next_link:
                # Extract next_page_token from the URL
                parsed = urllib.parse.urlparse(next_link['href'])
                qs = urllib.parse.parse_qs(parsed.query)
                next_page_token = qs.get('next_page_token', [None])[0]
                if not next_page_token:
                    break
            else:
                break

        return all_disputes


def sync_paypal_data(user, days_back: int = 30) -> dict:
    """Sync PayPal transactions, invoices, and disputes for a user."""
    try:
        connection = user.paypal_connection
    except PayPalConnection.DoesNotExist:
        raise ValueError('No PayPal connection found for this user')

    if not connection.is_active:
        raise ValueError('PayPal connection is inactive')

    client = PayPalClient(connection)
    stats = {'transactions_created': 0, 'transactions_updated': 0,
             'invoices_created': 0, 'invoices_updated': 0,
             'disputes_created': 0, 'disputes_updated': 0}

    # --- Transactions ---
    try:
        _sync_transactions(client, user, connection, days_back, stats)
    except Exception:
        logger.exception('Failed to sync PayPal transactions for %s', user.email)
        stats['transactions_error'] = 'Failed to sync transactions'

    # --- Invoices ---
    try:
        _sync_invoices(client, user, connection, stats)
    except Exception:
        logger.exception('Failed to sync PayPal invoices for %s', user.email)
        stats['invoices_error'] = 'Failed to sync invoices'

    # --- Disputes ---
    try:
        _sync_disputes(client, user, connection, stats)
    except Exception:
        logger.exception('Failed to sync PayPal disputes for %s', user.email)
        stats['disputes_error'] = 'Failed to sync disputes'

    # Update last_sync
    from django.utils import timezone as tz
    connection.last_sync = tz.now()
    connection.save(update_fields=['last_sync'])

    logger.info('PayPal sync complete for %s: %s', user.email, stats)
    return stats


def _sync_transactions(client, user, connection, days_back, stats):
    """Sync PayPal transactions."""
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=days_back)

    raw_transactions = client.fetch_transactions(start_date, end_date)
    for raw_tx in raw_transactions:
        tx_info = raw_tx.get('transaction_info', {})
        payer_info = raw_tx.get('payer_info', {})

        paypal_id = tx_info.get('transaction_id', '')
        if not paypal_id:
            continue

        amount_data = tx_info.get('transaction_amount', {})
        fee_data = tx_info.get('fee_amount', {})

        defaults = {
            'user': user,
            'connection': connection,
            'amount': Decimal(amount_data.get('value', '0')),
            'currency': amount_data.get('currency_code', 'USD'),
            'fee': Decimal(fee_data['value']) if fee_data.get('value') else None,
            'net': None,
            'event_code': tx_info.get('transaction_event_code', ''),
            'transaction_status': tx_info.get('transaction_status', ''),
            'description': tx_info.get('transaction_subject', ''),
            'note': tx_info.get('transaction_note', ''),
            'payer_email': payer_info.get('email_address', ''),
            'payer_name': _extract_payer_name(payer_info),
            'payer_id': payer_info.get('account_id', ''),
            'protection_eligibility': tx_info.get('protection_eligibility', ''),
            'invoice_id': tx_info.get('invoice_id', ''),
            'custom_field': tx_info.get('custom_field', ''),
            'initiation_date': tx_info.get('transaction_initiation_date', end_date.isoformat()),
            'updated_date': tx_info.get('transaction_updated_date'),
            'raw_data': raw_tx,
        }

        # Compute net if fee is available
        if defaults['fee'] is not None:
            defaults['net'] = defaults['amount'] + defaults['fee']  # fee is negative

        _, created = PayPalTransaction.objects.update_or_create(
            paypal_id=paypal_id, defaults=defaults
        )
        if created:
            stats['transactions_created'] += 1
        else:
            stats['transactions_updated'] += 1


def _sync_invoices(client, user, connection, stats):
    """Sync PayPal invoices."""
    raw_invoices = client.fetch_invoices()
    for raw_inv in raw_invoices:
        paypal_id = raw_inv.get('id', '')
        if not paypal_id:
            continue

        detail = raw_inv.get('detail', {})
        amount_data = detail.get('amount', {})
        due_amount = raw_inv.get('due_amount', {})
        primary_recipient = (raw_inv.get('primary_recipients') or [{}])[0] if raw_inv.get('primary_recipients') else {}
        billing_info = primary_recipient.get('billing_info', {})

        defaults = {
            'user': user,
            'connection': connection,
            'invoice_number': detail.get('invoice_number', ''),
            'status': raw_inv.get('status', ''),
            'amount_total': Decimal(amount_data.get('value', '0')),
            'amount_due': Decimal(due_amount['value']) if due_amount.get('value') else None,
            'currency': amount_data.get('currency_code', 'USD'),
            'merchant_memo': detail.get('memo', ''),
            'terms_and_conditions': detail.get('terms_and_conditions', ''),
            'recipient_email': billing_info.get('email_address', ''),
            'recipient_name': _extract_recipient_name(billing_info),
            'invoice_date': detail.get('invoice_date'),
            'due_date': detail.get('payment_term', {}).get('due_date'),
            'payments': raw_inv.get('payments', {}).get('transactions', []),
            'refunds': raw_inv.get('refunds', {}).get('transactions', []),
            'line_items': raw_inv.get('items', []),
            'raw_data': raw_inv,
        }

        _, created = PayPalInvoice.objects.update_or_create(
            paypal_id=paypal_id, defaults=defaults
        )
        if created:
            stats['invoices_created'] += 1
        else:
            stats['invoices_updated'] += 1


def _sync_disputes(client, user, connection, stats):
    """Sync PayPal disputes."""
    raw_disputes = client.fetch_disputes()
    for raw_disp in raw_disputes:
        paypal_id = raw_disp.get('dispute_id', '')
        if not paypal_id:
            continue

        dispute_amount = raw_disp.get('dispute_amount', {})
        disputed_txs = raw_disp.get('disputed_transactions', [])

        defaults = {
            'user': user,
            'connection': connection,
            'disputed_transaction_id': disputed_txs[0].get('seller_transaction_id', '') if disputed_txs else '',
            'reason': raw_disp.get('reason', ''),
            'status': raw_disp.get('status', ''),
            'dispute_amount': Decimal(dispute_amount['value']) if dispute_amount.get('value') else None,
            'currency': dispute_amount.get('currency_code', ''),
            'dispute_outcome': raw_disp.get('dispute_outcome', {}).get('outcome_code', ''),
            'dispute_life_cycle_stage': raw_disp.get('dispute_life_cycle_stage', ''),
            'created_date': raw_disp.get('create_time'),
            'updated_date': raw_disp.get('update_time'),
            'raw_data': raw_disp,
        }

        _, created = PayPalDispute.objects.update_or_create(
            paypal_id=paypal_id, defaults=defaults
        )
        if created:
            stats['disputes_created'] += 1
        else:
            stats['disputes_updated'] += 1


def _extract_payer_name(payer_info: dict) -> str:
    name = payer_info.get('payer_name', {})
    parts = [name.get('given_name', ''), name.get('surname', '')]
    return ' '.join(p for p in parts if p)


def _extract_recipient_name(billing_info: dict) -> str:
    name = billing_info.get('name', {})
    if isinstance(name, dict):
        parts = [name.get('given_name', ''), name.get('surname', '')]
        return ' '.join(p for p in parts if p)
    return str(name) if name else ''
