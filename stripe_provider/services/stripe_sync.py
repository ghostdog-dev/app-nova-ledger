import logging
from datetime import datetime, timedelta, timezone

import stripe
from django.utils import timezone as tz

from ..models import (
    StripeBalanceTransaction,
    StripeCharge,
    StripeConnection,
    StripeDispute,
    StripeInvoice,
    StripePayout,
    StripeSubscription,
)

logger = logging.getLogger(__name__)


def _ts_to_dt(ts):
    """Convert a Unix timestamp to a timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _paginate(list_method, **params):
    """Auto-paginate a Stripe list endpoint using starting_after."""
    all_items = []
    has_more = True
    starting_after = None

    while has_more:
        if starting_after:
            params['starting_after'] = starting_after

        response = list_method(**params)
        items = response.data
        all_items.extend(items)
        has_more = response.has_more

        if items:
            starting_after = items[-1].id

    return all_items


def _g(obj, attr, default=''):
    """Safe getattr for Stripe objects — avoids AttributeError on missing fields."""
    try:
        val = getattr(obj, attr, default)
        return val if val is not None else default
    except (AttributeError, KeyError):
        return default


def sync_balance_transactions(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe balance transactions."""
    params = {'api_key': access_token, 'limit': 100}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.BalanceTransaction.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict
        source = d.get('source', '')
        source_id = source if isinstance(source, str) else (source.get('id', '') if isinstance(source, dict) else '')

        _, was_created = StripeBalanceTransaction.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'amount': d.get('amount', 0),
                'currency': d.get('currency', ''),
                'fee': d.get('fee', 0),
                'net': d.get('net', 0),
                'type': d.get('type', ''),
                'status': d.get('status', ''),
                'description': d.get('description', '') or '',
                'source_id': source_id,
                'source_type': d.get('type', ''),
                'created_at_stripe': _ts_to_dt(d.get('created')),
                'available_on': _ts_to_dt(d.get('available_on')),
                'exchange_rate': d.get('exchange_rate', None),
                'raw_data': d,
            },
        )
        if was_created:
            created += 1

    logger.info('Balance transactions: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_charges(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe charges."""
    params = {'api_key': access_token, 'limit': 100}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.Charge.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict

        # Extract payment method details
        pm = d.get('payment_method_details') or {}
        if not isinstance(pm, dict):
            pm = dict(pm) if pm else {}
        card_info = pm.get('card') or {}
        if not isinstance(card_info, dict):
            card_info = dict(card_info) if card_info else {}

        # Extract billing details
        bd = d.get('billing_details') or {}
        if not isinstance(bd, dict):
            bd = dict(bd) if bd else {}

        # Extract metadata
        meta = d.get('metadata') or {}
        if not isinstance(meta, dict):
            meta = dict(meta) if meta else {}

        _, was_created = StripeCharge.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'amount': d.get('amount', 0),
                'amount_captured': d.get('amount_captured', 0) or 0,
                'amount_refunded': d.get('amount_refunded', 0) or 0,
                'currency': d.get('currency', ''),
                'status': d.get('status', ''),
                'paid': d.get('paid', False),
                'refunded': d.get('refunded', False),
                'disputed': d.get('disputed', False),
                'description': d.get('description', '') or '',
                'statement_descriptor': d.get('statement_descriptor', '') or '',
                'customer_id': d.get('customer', '') or '',
                'customer_email': bd.get('email', '') or '',
                'customer_name': bd.get('name', '') or '',
                'payment_method_type': pm.get('type', ''),
                'card_brand': card_info.get('brand', ''),
                'card_last4': card_info.get('last4', ''),
                'card_country': card_info.get('country', ''),
                'invoice_id': d.get('invoice', '') or '',
                'receipt_url': d.get('receipt_url', '') or '',
                'failure_code': d.get('failure_code', '') or '',
                'failure_message': d.get('failure_message', '') or '',
                'metadata': meta,
                'raw_data': d,
                'created_at_stripe': _ts_to_dt(d.get('created')),
            },
        )
        if was_created:
            created += 1

    logger.info('Charges: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_payouts(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe payouts."""
    params = {'api_key': access_token, 'limit': 100}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.Payout.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict
        arrival = d.get('arrival_date')

        _, was_created = StripePayout.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'amount': d.get('amount', 0),
                'currency': d.get('currency', ''),
                'status': d.get('status', ''),
                'arrival_date': _ts_to_dt(arrival).date() if arrival else None,
                'method': d.get('method', '') or '',
                'destination_type': d.get('type', '') or '',
                'bank_account_last4': '',  # populated below
                'automatic': d.get('automatic', True) if d.get('automatic') is not None else True,
                'failure_code': d.get('failure_code', '') or '',
                'failure_message': d.get('failure_message', '') or '',
                'raw_data': d,
                'created_at_stripe': _ts_to_dt(d.get('created')),
            },
        )
        if was_created:
            created += 1

    logger.info('Payouts: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_invoices(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe invoices."""
    params = {'api_key': access_token, 'limit': 100}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.Invoice.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict

        # Extract line items
        line_items_data = []
        lines = d.get('lines')
        if lines:
            lines_data = lines.get('data', []) if isinstance(lines, dict) else getattr(lines, 'data', [])
            for line in lines_data:
                ld = dict(line) if not isinstance(line, dict) else line
                period = ld.get('period')
                if period and not isinstance(period, dict):
                    period = dict(period)
                line_items_data.append({
                    'description': ld.get('description', '') or '',
                    'amount': ld.get('amount', 0),
                    'quantity': ld.get('quantity', 0),
                    'period': {
                        'start': period.get('start') if period else None,
                        'end': period.get('end') if period else None,
                    } if period else None,
                })

        # Extract status_transitions
        st = d.get('status_transitions') or {}
        if not isinstance(st, dict):
            st = dict(st) if st else {}

        _, was_created = StripeInvoice.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'number': d.get('number', '') or '',
                'status': d.get('status', '') or '',
                'amount_due': d.get('amount_due', 0) or 0,
                'amount_paid': d.get('amount_paid', 0) or 0,
                'amount_remaining': d.get('amount_remaining', 0) or 0,
                'subtotal': d.get('subtotal', 0) or 0,
                'tax': d.get('tax', 0) or 0,
                'total': d.get('total', 0) or 0,
                'currency': d.get('currency', '') or '',
                'customer_id': d.get('customer', '') or '',
                'customer_email': d.get('customer_email', '') or '',
                'customer_name': d.get('customer_name', '') or '',
                'invoice_date': _ts_to_dt(d.get('created')),
                'due_date': _ts_to_dt(d.get('due_date')),
                'paid_at': _ts_to_dt(st.get('paid_at')),
                'subscription_id': d.get('subscription', '') or '',
                'hosted_invoice_url': d.get('hosted_invoice_url', '') or '',
                'invoice_pdf': d.get('invoice_pdf', '') or '',
                'line_items': line_items_data,
                'raw_data': d,
            },
        )
        if was_created:
            created += 1

    logger.info('Invoices: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_subscriptions(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe subscriptions."""
    params = {'api_key': access_token, 'limit': 100, 'status': 'all'}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.Subscription.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict

        # Get plan details from the first item
        plan_amount = 0
        plan_currency = ''
        plan_interval = ''
        plan_interval_count = 1
        plan_product_name = ''

        sub_items = d.get('items')
        if sub_items:
            sub_items_data = sub_items.get('data', []) if isinstance(sub_items, dict) else getattr(sub_items, 'data', [])
            if sub_items_data:
                si = sub_items_data[0]
                if not isinstance(si, dict):
                    si = dict(si)
                price = si.get('price') or {}
                if not isinstance(price, dict):
                    price = dict(price)
                if price:
                    plan_amount = price.get('unit_amount', 0) or 0
                    plan_currency = price.get('currency', '') or ''
                    recurring = price.get('recurring') or {}
                    if not isinstance(recurring, dict):
                        recurring = dict(recurring) if recurring else {}
                    plan_interval = recurring.get('interval', '') if recurring else ''
                    plan_interval_count = recurring.get('interval_count', 1) if recurring else 1
                    product = price.get('product')
                    if isinstance(product, str):
                        plan_product_name = product
                    elif isinstance(product, dict):
                        plan_product_name = product.get('name', '')
                    elif product:
                        plan_product_name = getattr(product, 'name', '')

        _, was_created = StripeSubscription.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'status': d.get('status', ''),
                'customer_id': d.get('customer', '') or '',
                'customer_email': '',  # not directly on subscription
                'plan_amount': plan_amount,
                'plan_currency': plan_currency,
                'plan_interval': plan_interval,
                'plan_interval_count': plan_interval_count,
                'plan_product_name': plan_product_name,
                'current_period_start': _ts_to_dt(d.get('current_period_start')),
                'current_period_end': _ts_to_dt(d.get('current_period_end')),
                'cancel_at_period_end': d.get('cancel_at_period_end', False) or False,
                'canceled_at': _ts_to_dt(d.get('canceled_at')),
                'trial_start': _ts_to_dt(d.get('trial_start')),
                'trial_end': _ts_to_dt(d.get('trial_end')),
                'raw_data': d,
                'created_at_stripe': _ts_to_dt(d.get('created')),
            },
        )
        if was_created:
            created += 1

    logger.info('Subscriptions: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_disputes(user, connection, access_token, created_gte=None):
    """Fetch and store Stripe disputes."""
    params = {'api_key': access_token, 'limit': 100}
    if created_gte:
        params['created'] = {'gte': created_gte}
    items = _paginate(stripe.Dispute.list, **params)
    created = 0

    for item in items:
        d = item.to_dict()  # Convert Stripe object to plain dict

        _, was_created = StripeDispute.objects.update_or_create(
            stripe_id=d.get('id'),
            defaults={
                'user': user,
                'connection': connection,
                'charge_id': d.get('charge', '') or '',
                'amount': d.get('amount', 0),
                'currency': d.get('currency', ''),
                'status': d.get('status', ''),
                'reason': d.get('reason', '') or '',
                'evidence_due_by': _ts_to_dt(d.get('evidence_due_by')),
                'raw_data': d,
                'created_at_stripe': _ts_to_dt(d.get('created')),
            },
        )
        if was_created:
            created += 1

    logger.info('Disputes: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_stripe_data(user, days_back: int = 90):
    """Full sync of all Stripe data for a user."""
    try:
        connection = user.stripe_connection
    except StripeConnection.DoesNotExist:
        raise ValueError('No Stripe connection for this user')

    if not connection.is_active:
        raise ValueError('Stripe connection is inactive')

    # Pass access_token per-request (Stripe SDK uses api_key= kwarg)
    access_token = connection.access_token

    # Compute created_gte as Unix timestamp for date filtering
    created_gte = int((datetime.now(tz=timezone.utc) - timedelta(days=days_back)).timestamp())

    stats = {}

    sync_funcs = [
        ('balance_transactions', sync_balance_transactions),
        ('charges', sync_charges),
        ('payouts', sync_payouts),
        ('invoices', sync_invoices),
        ('subscriptions', sync_subscriptions),
        ('disputes', sync_disputes),
    ]

    for name, func in sync_funcs:
        try:
            stats[name] = func(user, connection, access_token, created_gte=created_gte)
        except Exception:
            logger.exception('Failed to sync %s for user %s', name, user.email)
            stats[name] = {'error': f'Failed to sync {name}'}

    # Update last_sync
    connection.last_sync = tz.now()
    connection.save(update_fields=['last_sync'])

    logger.info('Stripe sync completed for %s: %s', user.email, stats)
    return stats
