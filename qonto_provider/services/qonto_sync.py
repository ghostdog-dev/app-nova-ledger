import logging
from datetime import datetime

import httpx
from django.utils import timezone

from ..models import QontoBankAccount, QontoConnection, QontoTransaction

logger = logging.getLogger(__name__)

QONTO_API_BASE = 'https://thirdparty.qonto.com/v2'


class QontoClient:
    """Thin wrapper around the Qonto REST API using httpx."""

    def __init__(self, login: str, secret_key: str):
        self.login = login
        self.secret_key = secret_key
        self.client = httpx.Client(
            base_url=QONTO_API_BASE,
            headers={
                'Authorization': f'{login}:{secret_key}',
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def get_organization(self) -> dict:
        """GET /v2/organization -- verify credentials and get org info."""
        resp = self.client.get('/organization')
        resp.raise_for_status()
        return resp.json()

    def list_transactions(
        self,
        bank_account_id: str,
        status: list[str] | None = None,
        settled_at_from: str | None = None,
    ) -> list[dict]:
        """Paginate through all transactions for a bank account."""
        if status is None:
            status = ['completed']

        results = []
        page = 1
        per_page = 100

        while True:
            params: dict = {
                'slug': bank_account_id,
                'status[]': status,
                'per_page': per_page,
                'current_page': page,
            }
            if settled_at_from:
                params['settled_at_from'] = settled_at_from

            resp = self.client.get('/transactions', params=params)
            resp.raise_for_status()
            data = resp.json()

            transactions = data.get('transactions', [])
            results.extend(transactions)

            meta = data.get('meta', {})
            next_page = meta.get('next_page')
            if next_page is None:
                break
            page = next_page

        return results


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from Qonto."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _cents(value) -> int:
    """Convert amount to integer cents. Qonto returns amount_cents as integer."""
    if value is None:
        return 0
    return int(value)


def sync_qonto_data(user) -> dict:
    """Sync all Qonto data for a user. Returns stats dict."""
    try:
        connection = user.qonto_connection
    except QontoConnection.DoesNotExist:
        raise ValueError('No Qonto connection found for this user')

    if not connection.is_active:
        raise ValueError('Qonto connection is inactive')

    client = QontoClient(connection.login, connection.secret_key)
    stats = {'bank_accounts': 0, 'transactions': 0}

    try:
        # Get organization info and bank accounts
        try:
            org_data = client.get_organization()
            organization = org_data.get('organization', {})
            bank_accounts = organization.get('bank_accounts', [])
            stats['bank_accounts'] = _sync_bank_accounts(bank_accounts, user, connection)

            # Update org name on connection
            org_name = organization.get('name', '')
            if org_name and org_name != connection.organization_name:
                connection.organization_name = org_name
                connection.save(update_fields=['organization_name'])
        except Exception:
            logger.exception('Failed to sync Qonto organization/bank accounts for %s', user.email)
            stats['bank_accounts_error'] = 'Failed to sync bank accounts'

        # Sync transactions for each bank account
        try:
            total_tx = 0
            db_accounts = QontoBankAccount.objects.filter(user=user, connection=connection)
            for account in db_accounts:
                slug = account.slug or account.qonto_id
                raw_transactions = client.list_transactions(slug)
                total_tx += _sync_transactions(raw_transactions, user, connection)
            stats['transactions'] = total_tx
        except Exception:
            logger.exception('Failed to sync Qonto transactions for %s', user.email)
            stats['transactions_error'] = 'Failed to sync transactions'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Qonto sync for %s: %d bank accounts, %d transactions',
        user.email, stats['bank_accounts'], stats['transactions'],
    )
    return stats


def _sync_bank_accounts(raw_accounts: list[dict], user, connection: QontoConnection) -> int:
    """Sync bank accounts from Qonto org response. Returns count."""
    count = 0

    for acct in raw_accounts:
        QontoBankAccount.objects.update_or_create(
            qonto_id=acct['id'],
            defaults={
                'user': user,
                'connection': connection,
                'slug': acct.get('slug', ''),
                'name': acct.get('name', ''),
                'iban': acct.get('iban', ''),
                'bic': acct.get('bic', ''),
                'currency': acct.get('currency', 'EUR'),
                'balance_cents': _cents(acct.get('balance_cents')),
                'authorized_balance_cents': _cents(acct.get('authorized_balance_cents')),
                'status': acct.get('status', 'active'),
                'is_main': acct.get('is_main', False),
                'raw_data': acct,
            },
        )
        count += 1

    return count


def _sync_transactions(raw_transactions: list[dict], user, connection: QontoConnection) -> int:
    """Sync transactions from Qonto. Returns count of new/updated transactions."""
    count = 0

    for tx in raw_transactions:
        QontoTransaction.objects.update_or_create(
            qonto_id=tx['id'],
            defaults={
                'user': user,
                'connection': connection,
                'transaction_id': tx.get('transaction_id', ''),
                'amount_cents': _cents(tx.get('amount_cents')),
                'currency': tx.get('currency', 'EUR'),
                'side': tx.get('side', ''),
                'operation_type': tx.get('operation_type', ''),
                'status': tx.get('status', ''),
                'label': tx.get('label', ''),
                'counterparty_name': tx.get('counterparty_name', ''),
                'reference': tx.get('reference', ''),
                'note': tx.get('note', ''),
                'settled_at': _parse_dt(tx.get('settled_at')),
                'emitted_at': _parse_dt(tx.get('emitted_at')),
                'category': tx.get('category', ''),
                'attachment_ids': tx.get('attachment_ids', []),
                'label_ids': tx.get('label_ids', []),
                'card_last_digits': tx.get('card_last_digits', ''),
                'bank_account_id': tx.get('bank_account_id', ''),
                'raw_data': tx,
                'created_at_qonto': _parse_dt(tx['created_at']),
                'updated_at_qonto': _parse_dt(tx.get('updated_at')),
            },
        )
        count += 1

    return count
