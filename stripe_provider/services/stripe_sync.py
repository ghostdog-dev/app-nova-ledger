import logging
from datetime import datetime, timezone

import stripe

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


def sync_balance_transactions(user, connection, access_token):
    """Fetch and store Stripe balance transactions."""
    items = _paginate(stripe.BalanceTransaction.list, api_key=access_token, limit=100)
    created = 0

    for item in items:
        _, was_created = StripeBalanceTransaction.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': item.amount,
                'currency': item.currency,
                'fee': item.fee,
                'net': item.net,
                'type': item.type,
                'status': item.status,
                'description': item.description or '',
                'source_id': item.source if isinstance(item.source, str) else (item.source.id if item.source else ''),
                'source_type': item.type,
                'created_at_stripe': _ts_to_dt(item.created),
                'available_on': _ts_to_dt(item.available_on),
                'exchange_rate': item.exchange_rate,
                'raw_data': dict(item),
            },
        )
        if was_created:
            created += 1

    logger.info('Balance transactions: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_charges(user, connection, access_token):
    """Fetch and store Stripe charges."""
    items = _paginate(stripe.Charge.list, api_key=access_token, limit=100)
    created = 0

    for item in items:
        # Extract payment method details
        pm = item.payment_method_details or {}
        card_info = pm.get('card', {}) or {}

        _, was_created = StripeCharge.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': item.amount,
                'amount_captured': item.amount_captured or 0,
                'amount_refunded': item.amount_refunded or 0,
                'currency': item.currency,
                'status': item.status,
                'paid': item.paid,
                'refunded': item.refunded,
                'disputed': item.disputed,
                'description': item.description or '',
                'statement_descriptor': item.statement_descriptor or '',
                'customer_id': item.customer or '',
                'customer_email': (item.billing_details or {}).get('email', '') or '',
                'customer_name': (item.billing_details or {}).get('name', '') or '',
                'payment_method_type': pm.get('type', ''),
                'card_brand': card_info.get('brand', ''),
                'card_last4': card_info.get('last4', ''),
                'card_country': card_info.get('country', ''),
                'invoice_id': item.invoice or '',
                'receipt_url': item.receipt_url or '',
                'failure_code': item.failure_code or '',
                'failure_message': item.failure_message or '',
                'metadata': dict(item.metadata) if item.metadata else {},
                'raw_data': dict(item),
                'created_at_stripe': _ts_to_dt(item.created),
            },
        )
        if was_created:
            created += 1

    logger.info('Charges: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_payouts(user, connection, access_token):
    """Fetch and store Stripe payouts."""
    items = _paginate(stripe.Payout.list, api_key=access_token, limit=100)
    created = 0

    for item in items:
        _, was_created = StripePayout.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': item.amount,
                'currency': item.currency,
                'status': item.status,
                'arrival_date': _ts_to_dt(item.arrival_date).date() if item.arrival_date else None,
                'method': item.method or '',
                'destination_type': item.type or '',
                'bank_account_last4': '',  # populated below
                'automatic': item.automatic if item.automatic is not None else True,
                'failure_code': item.failure_code or '',
                'failure_message': item.failure_message or '',
                'raw_data': dict(item),
                'created_at_stripe': _ts_to_dt(item.created),
            },
        )
        if was_created:
            created += 1

    logger.info('Payouts: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_invoices(user, connection, access_token):
    """Fetch and store Stripe invoices."""
    items = _paginate(stripe.Invoice.list, api_key=access_token, limit=100)
    created = 0

    for item in items:
        # Extract line items
        line_items_data = []
        if item.lines and item.lines.data:
            for line in item.lines.data:
                line_items_data.append({
                    'description': line.description or '',
                    'amount': line.amount,
                    'quantity': line.quantity,
                    'period': {
                        'start': line.period.start if line.period else None,
                        'end': line.period.end if line.period else None,
                    } if line.period else None,
                })

        _, was_created = StripeInvoice.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'number': item.number or '',
                'status': item.status or '',
                'amount_due': item.amount_due or 0,
                'amount_paid': item.amount_paid or 0,
                'amount_remaining': item.amount_remaining or 0,
                'subtotal': item.subtotal or 0,
                'tax': item.tax,
                'total': item.total or 0,
                'currency': item.currency or '',
                'customer_id': item.customer or '',
                'customer_email': item.customer_email or '',
                'customer_name': item.customer_name or '',
                'invoice_date': _ts_to_dt(item.created),
                'due_date': _ts_to_dt(item.due_date),
                'paid_at': _ts_to_dt(item.status_transitions.paid_at) if item.status_transitions else None,
                'subscription_id': item.subscription or '',
                'hosted_invoice_url': item.hosted_invoice_url or '',
                'invoice_pdf': item.invoice_pdf or '',
                'line_items': line_items_data,
                'raw_data': dict(item),
            },
        )
        if was_created:
            created += 1

    logger.info('Invoices: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_subscriptions(user, connection, access_token):
    """Fetch and store Stripe subscriptions."""
    items = _paginate(stripe.Subscription.list, api_key=access_token, limit=100, status='all')
    created = 0

    for item in items:
        # Get plan details from the first item
        plan_amount = 0
        plan_currency = ''
        plan_interval = ''
        plan_interval_count = 1
        plan_product_name = ''

        if item.items and item.items.data:
            si = item.items.data[0]
            if si.price:
                plan_amount = si.price.unit_amount or 0
                plan_currency = si.price.currency or ''
                plan_interval = si.price.recurring.interval if si.price.recurring else ''
                plan_interval_count = si.price.recurring.interval_count if si.price.recurring else 1
            if si.price and si.price.product:
                # product might be expanded or just an ID
                if isinstance(si.price.product, str):
                    plan_product_name = si.price.product
                else:
                    plan_product_name = getattr(si.price.product, 'name', '')

        _, was_created = StripeSubscription.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'status': item.status,
                'customer_id': item.customer or '',
                'customer_email': '',  # not directly on subscription
                'plan_amount': plan_amount,
                'plan_currency': plan_currency,
                'plan_interval': plan_interval,
                'plan_interval_count': plan_interval_count,
                'plan_product_name': plan_product_name,
                'current_period_start': _ts_to_dt(item.current_period_start),
                'current_period_end': _ts_to_dt(item.current_period_end),
                'cancel_at_period_end': item.cancel_at_period_end or False,
                'canceled_at': _ts_to_dt(item.canceled_at),
                'trial_start': _ts_to_dt(item.trial_start),
                'trial_end': _ts_to_dt(item.trial_end),
                'raw_data': dict(item),
                'created_at_stripe': _ts_to_dt(item.created),
            },
        )
        if was_created:
            created += 1

    logger.info('Subscriptions: %d fetched, %d new', len(items), created)
    return {'fetched': len(items), 'created': created}


def sync_disputes(user, connection, access_token):
    """Fetch and store Stripe disputes."""
    items = _paginate(stripe.Dispute.list, api_key=access_token, limit=100)
    created = 0

    for item in items:
        _, was_created = StripeDispute.objects.update_or_create(
            stripe_id=item.id,
            defaults={
                'user': user,
                'connection': connection,
                'charge_id': item.charge or '',
                'amount': item.amount,
                'currency': item.currency,
                'status': item.status,
                'reason': item.reason or '',
                'evidence_due_by': _ts_to_dt(item.evidence_due_by),
                'raw_data': dict(item),
                'created_at_stripe': _ts_to_dt(item.created),
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
            stats[name] = func(user, connection, access_token)
        except Exception:
            logger.exception('Failed to sync %s for user %s', name, user.email)
            stats[name] = {'error': f'Failed to sync {name}'}

    # Update last_sync
    from django.utils import timezone as tz
    connection.last_sync = tz.now()
    connection.save(update_fields=['last_sync'])

    logger.info('Stripe sync completed for %s: %s', user.email, stats)
    return stats
