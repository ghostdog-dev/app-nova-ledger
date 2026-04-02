"""
Stripe Financial Connections service.

Handles: session creation, account linking, data sync (transactions, balances, ownership).
Uses the platform's STRIPE_SECRET_KEY (not the user's key).
"""
import logging
from datetime import datetime, timezone as dt_tz

import stripe as stripe_lib
from django.conf import settings
from django.utils import timezone

from ..models import FinancialAccount, FinancialTransaction

logger = logging.getLogger(__name__)


def _get_stripe_client():
    """Get a Stripe client using the platform secret key."""
    api_key = settings.STRIPE_SECRET_KEY
    if not api_key:
        raise ValueError('STRIPE_SECRET_KEY not configured')
    return stripe_lib.StripeClient(api_key)


def _ts_to_dt(timestamp):
    """Convert Unix timestamp to timezone-aware datetime, or None."""
    if not timestamp:
        return None
    return datetime.fromtimestamp(timestamp, tz=dt_tz.utc)


# ============================================================
# SESSION & ACCOUNT LINKING
# ============================================================

def get_or_create_stripe_customer(user):
    """Ensure the user has a Stripe Customer object (needed for FC sessions)."""
    client = _get_stripe_client()

    # Check if user already has a linked financial account with a customer ID
    existing = FinancialAccount.objects.filter(
        user=user, stripe_customer_id__gt='',
    ).first()
    if existing:
        return existing.stripe_customer_id

    # Create a new Stripe Customer
    customer = client.v1.customers.create(params={
        'email': user.email,
        'metadata': {'nova_ledger_user_id': str(user.pk)},
    })
    logger.info('[FC] Created Stripe customer %s for user %s', customer.id, user.email)
    return customer.id


def create_fc_session(user):
    """
    Create a Financial Connections Session.

    Returns the session object with client_secret for the frontend.
    The frontend uses Stripe.js collectFinancialConnectionsAccounts() with this secret.
    """
    client = _get_stripe_client()
    customer_id = get_or_create_stripe_customer(user)

    session = client.v1.financial_connections.sessions.create(params={
        'account_holder': {
            'type': 'customer',
            'customer': customer_id,
        },
        'permissions': ['transactions', 'balances', 'ownership'],
        'prefetch': ['transactions', 'balances', 'ownership'],
    })

    logger.info(
        '[FC] Created session %s for user %s (customer %s)',
        session.id, user.email, customer_id,
    )

    return {
        'session_id': session.id,
        'client_secret': session.client_secret,
        'customer_id': customer_id,
        'publishable_key': settings.STRIPE_PUBLISHABLE_KEY,
    }


def process_linked_accounts(user, session_id):
    """
    After the user completes the Stripe.js auth flow, retrieve the session
    and store the linked accounts in our DB.
    """
    client = _get_stripe_client()
    session = client.v1.financial_connections.sessions.retrieve(session_id)

    accounts_data = session.accounts.data if session.accounts else []
    if not accounts_data:
        logger.warning('[FC] Session %s has no linked accounts', session_id)
        return {'accounts_linked': 0}

    linked = 0
    for acct in accounts_data:
        fa, created = FinancialAccount.objects.update_or_create(
            stripe_account_id=acct.id,
            defaults={
                'user': user,
                'stripe_customer_id': getattr(session, 'account_holder', {}).get('customer', '') if isinstance(getattr(session, 'account_holder', None), dict) else '',
                'display_name': acct.display_name or '',
                'institution_name': acct.institution_name or '',
                'last4': acct.last4 or '',
                'category': acct.category or '',
                'subcategory': acct.subcategory or '',
                'status': acct.status or 'active',
                'permissions': list(acct.permissions) if acct.permissions else [],
                'raw_data': acct.to_dict() if hasattr(acct, 'to_dict') else {},
            },
        )
        linked += 1
        action = 'Created' if created else 'Updated'
        logger.info(
            '[FC] %s account %s (%s %s *%s)',
            action, acct.id, acct.institution_name, acct.display_name, acct.last4,
        )

    return {'accounts_linked': linked}


# ============================================================
# TRANSACTION SYNC
# ============================================================

def subscribe_to_transactions(account):
    """Subscribe an account to daily automatic transaction refreshes."""
    client = _get_stripe_client()
    client.v1.financial_connections.accounts.subscribe(
        account.stripe_account_id,
        params={'features': ['transactions']},
    )
    account.transaction_subscribed = True
    account.save(update_fields=['transaction_subscribed'])
    logger.info('[FC] Subscribed account %s to transaction refreshes', account.stripe_account_id)


def refresh_transactions(account):
    """Trigger an on-demand transaction refresh for an account."""
    client = _get_stripe_client()
    result = client.v1.financial_connections.accounts.refresh(
        account.stripe_account_id,
        params={'features': ['transactions']},
    )
    tx_refresh = getattr(result, 'transaction_refresh', None)
    if tx_refresh:
        account.transaction_refresh_status = tx_refresh.status
        account.save(update_fields=['transaction_refresh_status'])
    logger.info('[FC] Transaction refresh triggered for %s (status: %s)',
                account.stripe_account_id, tx_refresh.status if tx_refresh else 'unknown')
    return tx_refresh


def sync_transactions(account):
    """
    Fetch all transactions for an account and store them.
    Uses last_transaction_refresh_id to fetch only new/updated since last sync.
    """
    client = _get_stripe_client()

    params = {'account': account.stripe_account_id}
    # Incremental sync: only new transactions since last refresh
    if account.last_transaction_refresh_id:
        params['transaction_refresh'] = {'after': account.last_transaction_refresh_id}

    created_count = 0
    updated_count = 0
    last_refresh_id = account.last_transaction_refresh_id

    # Paginate through all transactions
    has_more = True
    starting_after = None

    while has_more:
        list_params = dict(params)
        if starting_after:
            list_params['starting_after'] = starting_after

        result = client.v1.financial_connections.transactions.list(params=list_params)

        for tx in result.data:
            status_transitions = tx.status_transitions if hasattr(tx, 'status_transitions') else None

            ft, created = FinancialTransaction.objects.update_or_create(
                stripe_transaction_id=tx.id,
                defaults={
                    'account': account,
                    'user': account.user,
                    'amount': tx.amount,
                    'currency': tx.currency or '',
                    'description': tx.description or '',
                    'status': tx.status or 'posted',
                    'transacted_at': _ts_to_dt(tx.transacted_at),
                    'posted_at': _ts_to_dt(status_transitions.posted_at) if status_transitions else None,
                    'void_at': _ts_to_dt(status_transitions.void_at) if status_transitions else None,
                    'transaction_refresh_id': tx.transaction_refresh or '',
                    'raw_data': tx.to_dict() if hasattr(tx, 'to_dict') else {},
                },
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

            # Track the latest refresh ID
            if tx.transaction_refresh and tx.transaction_refresh > (last_refresh_id or ''):
                last_refresh_id = tx.transaction_refresh

            starting_after = tx.id

        has_more = result.has_more

    # Update account with latest refresh ID
    if last_refresh_id != account.last_transaction_refresh_id:
        account.last_transaction_refresh_id = last_refresh_id or ''
        account.save(update_fields=['last_transaction_refresh_id'])

    logger.info(
        '[FC] Synced transactions for %s: %d created, %d updated',
        account.stripe_account_id, created_count, updated_count,
    )
    return {'created': created_count, 'updated': updated_count}


# ============================================================
# BALANCE SYNC
# ============================================================

def refresh_balances(account):
    """Refresh balance data for an account."""
    client = _get_stripe_client()
    result = client.v1.financial_connections.accounts.refresh(
        account.stripe_account_id,
        params={'features': ['balance']},
    )

    balance = getattr(result, 'balance', None)
    if balance:
        # StripeObjects need .to_dict() to be JSON-serializable
        current = getattr(balance, 'current', None)
        account.balance_current = current.to_dict() if hasattr(current, 'to_dict') else current
        cash = getattr(balance, 'cash', None)
        if cash:
            avail = getattr(cash, 'available', None)
            account.balance_available = avail.to_dict() if hasattr(avail, 'to_dict') else avail
        else:
            account.balance_available = None
        account.balance_type = getattr(balance, 'type', '') or ''
        account.balance_as_of = _ts_to_dt(getattr(balance, 'as_of', None))

    balance_refresh = getattr(result, 'balance_refresh', None)
    if balance_refresh:
        account.balance_refresh_status = balance_refresh.status

    account.save(update_fields=[
        'balance_current', 'balance_available', 'balance_type',
        'balance_as_of', 'balance_refresh_status',
    ])

    logger.info('[FC] Balance refresh for %s: %s', account.stripe_account_id, balance)
    return {
        'current': account.balance_current,
        'available': account.balance_available,
        'as_of': account.balance_as_of.isoformat() if account.balance_as_of else None,
    }


# ============================================================
# OWNERSHIP SYNC
# ============================================================

def refresh_ownership(account):
    """Refresh ownership (holder) data for an account."""
    client = _get_stripe_client()

    # Trigger refresh
    client.v1.financial_connections.accounts.refresh(
        account.stripe_account_id,
        params={'features': ['ownership']},
    )

    # Retrieve with ownership expanded
    result = client.v1.financial_connections.accounts.retrieve(
        account.stripe_account_id,
        params={'expand': ['ownership']},
    )

    ownership = getattr(result, 'ownership', None)
    owners = []
    if ownership and hasattr(ownership, 'owners'):
        owners_data = ownership.owners.data if hasattr(ownership.owners, 'data') else []
        for owner in owners_data:
            owners.append({
                'name': getattr(owner, 'name', ''),
                'email': getattr(owner, 'email', ''),
                'phone': getattr(owner, 'phone', ''),
                'raw_address': getattr(owner, 'raw_address', ''),
            })

    account.ownership_data = owners
    ownership_refresh = getattr(result, 'ownership_refresh', None)
    account.ownership_refresh_status = ownership_refresh.status if ownership_refresh else ''
    account.save(update_fields=['ownership_data', 'ownership_refresh_status'])

    logger.info('[FC] Ownership refresh for %s: %d owners', account.stripe_account_id, len(owners))
    return owners


# ============================================================
# FULL SYNC
# ============================================================

def sync_all(user):
    """
    Sync all data for all active financial accounts of a user.
    Returns combined stats.
    """
    accounts = FinancialAccount.objects.filter(user=user, status=FinancialAccount.Status.ACTIVE)

    if not accounts.exists():
        return {'error': 'No active financial accounts. Link a bank account first.'}

    stats = {
        'accounts': 0,
        'transactions_created': 0,
        'transactions_updated': 0,
        'balances_refreshed': 0,
        'ownership_refreshed': 0,
    }

    for account in accounts:
        stats['accounts'] += 1
        permissions = account.permissions or []

        # Transactions
        if 'transactions' in permissions:
            try:
                tx_stats = sync_transactions(account)
                stats['transactions_created'] += tx_stats['created']
                stats['transactions_updated'] += tx_stats['updated']
            except Exception as e:
                logger.error('[FC] Transaction sync failed for %s: %r', account.stripe_account_id, e)

        # Balances
        if 'balances' in permissions:
            try:
                refresh_balances(account)
                stats['balances_refreshed'] += 1
            except Exception as e:
                logger.error('[FC] Balance refresh failed for %s: %r', account.stripe_account_id, e)

        # Ownership
        if 'ownership' in permissions:
            try:
                refresh_ownership(account)
                stats['ownership_refreshed'] += 1
            except Exception as e:
                logger.error('[FC] Ownership refresh failed for %s: %r', account.stripe_account_id, e)

    logger.info('[FC] Full sync for user %s: %s', user.email, stats)
    return stats


def disconnect_account(account):
    """Disconnect a financial account."""
    client = _get_stripe_client()

    # Unsubscribe from transactions if subscribed
    if account.transaction_subscribed:
        try:
            client.v1.financial_connections.accounts.unsubscribe(
                account.stripe_account_id,
                params={'features': ['transactions']},
            )
        except Exception as e:
            logger.warning('[FC] Failed to unsubscribe %s: %s', account.stripe_account_id, e)

    # Disconnect on Stripe side
    client.v1.financial_connections.accounts.disconnect(account.stripe_account_id)

    account.status = FinancialAccount.Status.DISCONNECTED
    account.transaction_subscribed = False
    account.save(update_fields=['status', 'transaction_subscribed'])

    logger.info('[FC] Disconnected account %s', account.stripe_account_id)
