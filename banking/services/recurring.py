"""Detect recurring transactions from bank data patterns."""
import logging
from collections import defaultdict
from django.utils.text import slugify

from banking.models import BankTransaction
from banking.services.utils import normalize_vendor

logger = logging.getLogger(__name__)


def detect_recurring(user):
    """
    Detect recurring transactions by analyzing vendor patterns.
    Groups by normalized vendor, checks date intervals and amount similarity.
    """
    txs = list(
        BankTransaction.objects.filter(user=user, value__lt=0, coming=False)
        .select_related('account')
        .order_by('date')
    )

    # Group by normalized vendor + currency
    by_vendor = defaultdict(list)
    for tx in txs:
        vendor = normalize_vendor(tx.simplified_wording or tx.original_wording or '')
        currency = tx.account.currency if tx.account else 'EUR'
        if vendor:
            by_vendor[(vendor, currency)].append(tx)

    recurring_groups = 0
    recurring_txs = 0

    for (vendor, currency), vendor_txs in by_vendor.items():
        if len(vendor_txs) < 3:
            continue

        # Sort by date
        vendor_txs.sort(key=lambda t: t.date)

        # Compute intervals between consecutive transactions
        intervals = []
        for i in range(1, len(vendor_txs)):
            delta = (vendor_txs[i].date - vendor_txs[i-1].date).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        # Check if intervals are regular
        period = _detect_period(intervals)
        if not period:
            continue

        # Check amount similarity (within 20% tolerance)
        amounts = [abs(float(t.value)) for t in vendor_txs]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount == 0:
            continue
        amount_variance = max(abs(a - avg_amount) / avg_amount for a in amounts)
        if amount_variance > 0.20:
            continue

        # Mark as recurring
        group_id = f'{slugify(vendor)}_{period}_{currency.lower()}'
        for tx in vendor_txs:
            tx.is_recurring = True
            tx.recurring_group_id = group_id

        BankTransaction.objects.bulk_update(
            vendor_txs, ['is_recurring', 'recurring_group_id'], batch_size=100
        )

        recurring_groups += 1
        recurring_txs += len(vendor_txs)
        logger.info('[Recurring] Detected: %s (%s, %d txs, ~%.2f %s)', vendor, period, len(vendor_txs), avg_amount, currency)

    logger.info('[Recurring] %d groups, %d transactions', recurring_groups, recurring_txs)
    return {'recurring_groups': recurring_groups, 'recurring_transactions': recurring_txs}


def _detect_period(intervals):
    """Given list of day intervals, return period name or None."""
    if not intervals:
        return None
    avg = sum(intervals) / len(intervals)
    if avg == 0:
        return None
    std = (sum((i - avg) ** 2 for i in intervals) / len(intervals)) ** 0.5
    # Too much variance = not recurring
    if std / avg > 0.3:
        return None
    if 5 <= avg <= 10:
        return 'weekly'
    if 12 <= avg <= 18:
        return 'biweekly'
    if 25 <= avg <= 35:
        return 'monthly'
    if 85 <= avg <= 100:
        return 'quarterly'
    if 350 <= avg <= 380:
        return 'annual'
    return None
