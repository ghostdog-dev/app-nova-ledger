import logging
from datetime import date, timedelta
from decimal import Decimal

from django.utils import timezone

from ..models import BankAccount, BankConnection, BankTransaction, PowensUser
from .powens_client import PowensClient

logger = logging.getLogger(__name__)


def sync_bank_data(user, days=90):
    """Fetch accounts and transactions from Powens for a user.

    Args:
        user: The Django user to sync data for.
        days: Number of days of transaction history to fetch (default 90).

    Returns:
        dict with sync statistics.
    """
    try:
        powens_user = user.powens
    except PowensUser.DoesNotExist:
        raise ValueError('User has no Powens account linked. Connect a bank first.')

    client = PowensClient(auth_token=powens_user.auth_token)
    stats = {
        'connections_synced': 0,
        'accounts_synced': 0,
        'transactions_created': 0,
        'transactions_updated': 0,
    }

    # --- Sync connections ---
    try:
        connections_data = client.list_connections()
    except Exception:
        logger.exception('Failed to fetch connections from Powens for user %s', user.email)
        raise

    connections_list = connections_data.get('connections', [])
    for conn_data in connections_list:
        conn, created = BankConnection.objects.update_or_create(
            powens_connection_id=conn_data['id'],
            defaults={
                'user': user,
                'bank_name': conn_data.get('connector', {}).get('name', ''),
                'state': conn_data.get('state') or '',
                'last_sync': timezone.now(),
            },
        )
        stats['connections_synced'] += 1
        logger.info(
            'Connection %s (%s) — state=%s',
            conn.powens_connection_id,
            conn.bank_name,
            conn.state,
        )

    # --- Sync accounts ---
    try:
        accounts_data = client.list_accounts()
    except Exception:
        logger.exception('Failed to fetch accounts from Powens for user %s', user.email)
        raise

    accounts_list = accounts_data.get('accounts', [])
    account_map = {}  # powens_account_id -> BankAccount

    for acct_data in accounts_list:
        # Find the parent connection
        powens_conn_id = acct_data.get('id_connection')
        try:
            connection = BankConnection.objects.get(powens_connection_id=powens_conn_id)
        except BankConnection.DoesNotExist:
            logger.warning(
                'Account %s references unknown connection %s — skipping',
                acct_data.get('id'),
                powens_conn_id,
            )
            continue

        acct, created = BankAccount.objects.update_or_create(
            powens_account_id=acct_data['id'],
            defaults={
                'connection': connection,
                'user': user,
                'name': acct_data.get('name', ''),
                'iban': acct_data.get('iban') or '',
                'balance': Decimal(str(acct_data['balance'])) if acct_data.get('balance') is not None else None,
                'currency': acct_data.get('currency', {}).get('id', 'EUR') if isinstance(acct_data.get('currency'), dict) else acct_data.get('currency', 'EUR'),
                'account_type': acct_data.get('type', {}).get('name', '') if isinstance(acct_data.get('type'), dict) else str(acct_data.get('type', '')),
                'disabled': bool(acct_data.get('disabled')),
                'last_update': timezone.now(),
            },
        )
        account_map[acct.powens_account_id] = acct
        stats['accounts_synced'] += 1
        logger.info('Account %s (%s) — balance=%s', acct.powens_account_id, acct.name, acct.balance)

    # --- Sync transactions per account ---
    min_date = (date.today() - timedelta(days=days)).isoformat()

    for powens_acct_id, acct in account_map.items():
        if acct.disabled:
            logger.info('Skipping disabled account %s', acct.name)
            continue

        try:
            txn_data = client.list_transactions(
                account_id=powens_acct_id,
                min_date=min_date,
            )
        except Exception:
            logger.exception(
                'Failed to fetch transactions for account %s (%s)',
                powens_acct_id,
                acct.name,
            )
            continue

        transactions_list = txn_data.get('transactions', [])
        logger.info(
            'Fetched %d transactions for account %s (%s)',
            len(transactions_list),
            powens_acct_id,
            acct.name,
        )

        for txn in transactions_list:
            _, created = BankTransaction.objects.update_or_create(
                powens_transaction_id=txn['id'],
                defaults={
                    'account': acct,
                    'user': user,
                    'date': txn.get('date', date.today().isoformat()),
                    'value': Decimal(str(txn.get('value', 0))),
                    'original_wording': txn.get('original_wording', ''),
                    'simplified_wording': txn.get('simplified_wording', ''),
                    'transaction_type': txn.get('type', ''),
                    'coming': txn.get('coming', False),
                    'card': txn.get('card') or '',
                    'counterparty_label': _get_nested(txn, 'counterparty', 'label'),
                    'counterparty_iban': _get_nested(txn, 'counterparty', 'iban'),
                    'rdate': txn.get('rdate'),
                    'original_value': Decimal(str(txn['original_value'])) if txn.get('original_value') is not None else None,
                    'original_currency': txn.get('original_currency', {}).get('id', '') if isinstance(txn.get('original_currency'), dict) else '',
                    'category_id': txn.get('id_category'),
                    'raw_data': txn,
                },
            )
            if created:
                stats['transactions_created'] += 1
            else:
                stats['transactions_updated'] += 1

    logger.info('Sync complete for user %s: %s', user.email, stats)
    return stats


def _get_nested(data, *keys):
    """Safely traverse nested dicts, returning empty string on missing keys."""
    current = data
    for key in keys:
        if isinstance(current, dict):
            current = current.get(key)
        else:
            return ''
    return current or ''
