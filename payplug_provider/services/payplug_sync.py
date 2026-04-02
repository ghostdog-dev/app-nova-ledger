import logging
from datetime import datetime, timezone

import payplug
from django.utils import timezone as dj_timezone

from ..models import PayPlugConnection, PayPlugPayment, PayPlugRefund

logger = logging.getLogger(__name__)


class PayPlugClient:
    """Thin wrapper around the PayPlug Python SDK."""

    def __init__(self, secret_key: str):
        payplug.set_secret_key(secret_key)
        payplug.set_api_version("2019-08-06")

    def verify_key(self):
        """List 1 payment to verify the secret key is valid."""
        payplug.Payment.list(per_page=1, page=0)

    def list_all_payments(self) -> list:
        """Paginate through all payments."""
        all_payments = []
        page = 0
        while True:
            result = payplug.Payment.list(per_page=100, page=page)
            all_payments.extend(result)
            if not result.has_more:
                break
            page += 1
        return all_payments

    def list_refunds_for_payment(self, payment_id: str) -> list:
        """List all refunds for a given payment."""
        return list(payplug.Refund.list(payment_id))


def _ts_to_dt(ts) -> datetime | None:
    """Convert Unix timestamp (int) to timezone-aware datetime."""
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _resource_to_dict(resource) -> dict:
    """Convert a PayPlug SDK resource to a plain dict for raw_data storage."""
    try:
        return dict(resource)
    except (TypeError, ValueError):
        pass
    try:
        return {k: v for k, v in resource.__dict__.items() if not k.startswith('_')}
    except AttributeError:
        return {}


def sync_payplug_data(user) -> dict:
    """Sync all PayPlug data for a user. Returns stats dict."""
    try:
        connection = user.payplug_connection
    except PayPlugConnection.DoesNotExist:
        raise ValueError('No PayPlug connection found for this user')

    if not connection.is_active:
        raise ValueError('PayPlug connection is inactive')

    client = PayPlugClient(connection.secret_key)
    stats = {'payments': 0, 'refunds': 0}

    # Sync payments
    try:
        stats['payments'] = _sync_payments(client, user, connection)
    except Exception:
        logger.exception('Failed to sync PayPlug payments for %s', user.email)
        stats['payments_error'] = 'Failed to sync payments'

    # Sync refunds (for each payment)
    try:
        stats['refunds'] = _sync_refunds(client, user, connection)
    except Exception:
        logger.exception('Failed to sync PayPlug refunds for %s', user.email)
        stats['refunds_error'] = 'Failed to sync refunds'

    # Update last_sync
    connection.last_sync = dj_timezone.now()
    connection.save(update_fields=['last_sync'])

    logger.info(
        'PayPlug sync for %s: %d payments, %d refunds',
        user.email, stats['payments'], stats['refunds'],
    )
    return stats


def _sync_payments(client: PayPlugClient, user, connection: PayPlugConnection) -> int:
    """Sync payments from PayPlug. Returns count of new/updated payments."""
    raw_payments = client.list_all_payments()
    count = 0

    for p in raw_payments:
        # Extract card details
        card = getattr(p, 'card', None) or {}
        if not isinstance(card, dict):
            try:
                card = dict(card)
            except (TypeError, ValueError):
                card = {}

        # Extract billing details
        billing = getattr(p, 'billing', None) or {}
        if not isinstance(billing, dict):
            try:
                billing = dict(billing)
            except (TypeError, ValueError):
                billing = {}

        # Extract failure details
        failure = getattr(p, 'failure', None) or {}
        if not isinstance(failure, dict):
            try:
                failure = dict(failure)
            except (TypeError, ValueError):
                failure = {}

        PayPlugPayment.objects.update_or_create(
            payplug_id=p.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': p.amount,
                'amount_refunded': getattr(p, 'amount_refunded', 0) or 0,
                'currency': getattr(p, 'currency', 'EUR') or 'EUR',
                'is_paid': getattr(p, 'is_paid', False),
                'is_refunded': getattr(p, 'is_refunded', False),
                'is_3ds': getattr(p, 'is_3ds', None),
                'description': getattr(p, 'description', '') or '',
                # Card details
                'card_last4': card.get('last4', '') or '',
                'card_brand': card.get('brand', '') or '',
                'card_country': card.get('country', '') or '',
                'card_exp_month': card.get('exp_month'),
                'card_exp_year': card.get('exp_year'),
                # Billing details
                'billing_email': billing.get('email', '') or '',
                'billing_first_name': billing.get('first_name', '') or '',
                'billing_last_name': billing.get('last_name', '') or '',
                # Failure details
                'failure_code': failure.get('code', '') or '',
                'failure_message': failure.get('message', '') or '',
                # Installment plan
                'installment_plan_id': getattr(p, 'installment_plan_id', '') or '',
                # Metadata
                'metadata': getattr(p, 'metadata', {}) or {},
                # Dates
                'created_at_payplug': _ts_to_dt(p.created_at),
                'paid_at': _ts_to_dt(getattr(p, 'paid_at', None)),
                'raw_data': _resource_to_dict(p),
            },
        )
        count += 1

    return count


def _sync_refunds(client: PayPlugClient, user, connection: PayPlugConnection) -> int:
    """Sync refunds for all payments from PayPlug."""
    payments = PayPlugPayment.objects.filter(user=user, connection=connection)
    count = 0

    for payment in payments:
        try:
            raw_refunds = client.list_refunds_for_payment(payment.payplug_id)
        except Exception:
            logger.exception('Failed to list refunds for payment %s', payment.payplug_id)
            continue

        for r in raw_refunds:
            PayPlugRefund.objects.update_or_create(
                payplug_id=r.id,
                defaults={
                    'user': user,
                    'connection': connection,
                    'payment_id': getattr(r, 'payment_id', payment.payplug_id),
                    'amount': r.amount,
                    'currency': getattr(r, 'currency', 'EUR') or 'EUR',
                    'metadata': getattr(r, 'metadata', {}) or {},
                    'created_at_payplug': _ts_to_dt(r.created_at),
                    'raw_data': _resource_to_dict(r),
                },
            )
            count += 1

    return count
