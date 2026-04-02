import logging
from datetime import date, datetime

import gocardless_pro
from django.utils import timezone

from ..models import (
    GoCardlessConnection,
    GoCardlessMandate,
    GoCardlessPayment,
    GoCardlessPayout,
    GoCardlessRefund,
    GoCardlessSubscription,
)

logger = logging.getLogger(__name__)


def _record_to_dict(record) -> dict:
    """Convert a gocardless_pro SDK object to a serialisable dict."""
    raw = {}
    for attr in dir(record):
        if attr.startswith('_'):
            continue
        try:
            value = getattr(record, attr)
            if callable(value):
                continue
            # Convert nested SDK objects
            if hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, list, dict, type(None))):
                value = _record_to_dict(value)
            raw[attr] = value
        except Exception:
            pass
    return raw


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from GoCardless."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD date string from GoCardless."""
    if not value:
        return None
    return date.fromisoformat(value)


class GoCardlessClient:
    """Wrapper around the gocardless_pro SDK."""

    def __init__(self, access_token: str, environment: str = 'sandbox'):
        self.client = gocardless_pro.Client(
            access_token=access_token,
            environment=environment,
        )

    def verify_token(self):
        """List 1 payment to verify the token works."""
        self.client.payments.list(params={"limit": 1})

    def list_all_payments(self, created_gte: str | None = None) -> list:
        params = {}
        if created_gte:
            params["created_at[gte]"] = created_gte
        return list(self.client.payments.all(params=params))

    def list_all_mandates(self, created_gte: str | None = None) -> list:
        params = {}
        if created_gte:
            params["created_at[gte]"] = created_gte
        return list(self.client.mandates.all(params=params))

    def list_all_subscriptions(self, created_gte: str | None = None) -> list:
        params = {}
        if created_gte:
            params["created_at[gte]"] = created_gte
        return list(self.client.subscriptions.all(params=params))

    def list_all_payouts(self, created_gte: str | None = None) -> list:
        params = {}
        if created_gte:
            params["created_at[gte]"] = created_gte
        return list(self.client.payouts.all(params=params))

    def list_all_refunds(self, created_gte: str | None = None) -> list:
        params = {}
        if created_gte:
            params["created_at[gte]"] = created_gte
        return list(self.client.refunds.all(params=params))


def sync_gocardless_data(user) -> dict:
    """Sync all GoCardless data for a user. Returns stats dict."""
    try:
        connection = user.gocardless_connection
    except GoCardlessConnection.DoesNotExist:
        raise ValueError('No GoCardless connection found for this user')

    if not connection.is_active:
        raise ValueError('GoCardless connection is inactive')

    client = GoCardlessClient(connection.access_token, connection.environment)
    stats = {'payments': 0, 'mandates': 0, 'subscriptions': 0, 'payouts': 0, 'refunds': 0}

    # Sync payments
    try:
        stats['payments'] = _sync_payments(client, user, connection)
    except Exception:
        logger.exception('Failed to sync GoCardless payments for %s', user.email)
        stats['payments_error'] = 'Failed to sync payments'

    # Sync mandates
    try:
        stats['mandates'] = _sync_mandates(client, user, connection)
    except Exception:
        logger.exception('Failed to sync GoCardless mandates for %s', user.email)
        stats['mandates_error'] = 'Failed to sync mandates'

    # Sync subscriptions
    try:
        stats['subscriptions'] = _sync_subscriptions(client, user, connection)
    except Exception:
        logger.exception('Failed to sync GoCardless subscriptions for %s', user.email)
        stats['subscriptions_error'] = 'Failed to sync subscriptions'

    # Sync payouts
    try:
        stats['payouts'] = _sync_payouts(client, user, connection)
    except Exception:
        logger.exception('Failed to sync GoCardless payouts for %s', user.email)
        stats['payouts_error'] = 'Failed to sync payouts'

    # Sync refunds
    try:
        stats['refunds'] = _sync_refunds(client, user, connection)
    except Exception:
        logger.exception('Failed to sync GoCardless refunds for %s', user.email)
        stats['refunds_error'] = 'Failed to sync refunds'

    # Update last_sync
    connection.last_sync = timezone.now()
    connection.save(update_fields=['last_sync'])

    logger.info(
        'GoCardless sync for %s: %d payments, %d mandates, %d subscriptions, %d payouts, %d refunds',
        user.email, stats['payments'], stats['mandates'],
        stats['subscriptions'], stats['payouts'], stats['refunds'],
    )
    return stats


def _sync_payments(client: GoCardlessClient, user, connection: GoCardlessConnection) -> int:
    """Sync payments from GoCardless. Returns count of new/updated payments."""
    raw_payments = client.list_all_payments()
    count = 0

    for p in raw_payments:
        links = p.links
        GoCardlessPayment.objects.update_or_create(
            gocardless_id=p.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': p.amount,
                'amount_refunded': p.amount_refunded or 0,
                'currency': p.currency or '',
                'status': p.status or '',
                'charge_date': _parse_date(p.charge_date),
                'reference': p.reference or '',
                'description': p.description or '',
                'scheme': getattr(p, 'scheme', '') or '',
                'retry_if_possible': getattr(p, 'retry_if_possible', True) or False,
                'mandate_id': getattr(links, 'mandate', '') or '',
                'subscription_id': getattr(links, 'subscription', '') or '',
                'payout_id': getattr(links, 'payout', '') or '',
                'metadata': p.metadata or {},
                'created_at_gocardless': _parse_dt(p.created_at),
                'raw_data': _record_to_dict(p),
            },
        )
        count += 1

    return count


def _sync_mandates(client: GoCardlessClient, user, connection: GoCardlessConnection) -> int:
    """Sync mandates from GoCardless."""
    raw_mandates = client.list_all_mandates()
    count = 0

    for m in raw_mandates:
        links = m.links
        GoCardlessMandate.objects.update_or_create(
            gocardless_id=m.id,
            defaults={
                'user': user,
                'connection': connection,
                'reference': m.reference or '',
                'status': m.status or '',
                'scheme': m.scheme or '',
                'next_possible_charge_date': _parse_date(m.next_possible_charge_date),
                'customer_id': getattr(links, 'customer', '') or '',
                'customer_bank_account_id': getattr(links, 'customer_bank_account', '') or '',
                'metadata': m.metadata or {},
                'created_at_gocardless': _parse_dt(m.created_at),
                'raw_data': _record_to_dict(m),
            },
        )
        count += 1

    return count


def _sync_subscriptions(client: GoCardlessClient, user, connection: GoCardlessConnection) -> int:
    """Sync subscriptions from GoCardless."""
    raw_subscriptions = client.list_all_subscriptions()
    count = 0

    for s in raw_subscriptions:
        links = s.links
        GoCardlessSubscription.objects.update_or_create(
            gocardless_id=s.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': s.amount,
                'currency': s.currency or '',
                'status': s.status or '',
                'name': s.name or '',
                'start_date': _parse_date(s.start_date),
                'end_date': _parse_date(s.end_date),
                'interval': s.interval or 1,
                'interval_unit': s.interval_unit or '',
                'day_of_month': s.day_of_month,
                'mandate_id': getattr(links, 'mandate', '') or '',
                'upcoming_payments': s.upcoming_payments or [],
                'metadata': s.metadata or {},
                'created_at_gocardless': _parse_dt(s.created_at),
                'raw_data': _record_to_dict(s),
            },
        )
        count += 1

    return count


def _sync_payouts(client: GoCardlessClient, user, connection: GoCardlessConnection) -> int:
    """Sync payouts from GoCardless."""
    raw_payouts = client.list_all_payouts()
    count = 0

    for po in raw_payouts:
        GoCardlessPayout.objects.update_or_create(
            gocardless_id=po.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': po.amount,
                'currency': po.currency or '',
                'deducted_fees': po.deducted_fees or 0,
                'status': po.status or '',
                'arrival_date': _parse_date(po.arrival_date),
                'reference': po.reference or '',
                'payout_type': po.payout_type or '',
                'created_at_gocardless': _parse_dt(po.created_at),
                'raw_data': _record_to_dict(po),
            },
        )
        count += 1

    return count


def _sync_refunds(client: GoCardlessClient, user, connection: GoCardlessConnection) -> int:
    """Sync refunds from GoCardless."""
    raw_refunds = client.list_all_refunds()
    count = 0

    for r in raw_refunds:
        links = r.links
        GoCardlessRefund.objects.update_or_create(
            gocardless_id=r.id,
            defaults={
                'user': user,
                'connection': connection,
                'amount': r.amount,
                'currency': r.currency or '',
                'status': r.status or '',
                'reference': r.reference or '',
                'payment_id': getattr(links, 'payment', '') or '',
                'metadata': r.metadata or {},
                'created_at_gocardless': _parse_dt(r.created_at),
                'raw_data': _record_to_dict(r),
            },
        )
        count += 1

    return count
