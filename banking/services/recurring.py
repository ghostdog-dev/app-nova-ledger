"""Detect recurring transactions from bank data patterns."""
import json
import logging
import os
from collections import defaultdict

from django.conf import settings
from django.utils.text import slugify

from banking.models import BankTransaction
from banking.services.utils import normalize_vendor

logger = logging.getLogger(__name__)


def detect_recurring(user):
    """
    Detect recurring transactions by analyzing vendor patterns.
    Groups by normalized vendor, checks date intervals and amount similarity.
    Ambiguous cases are sent to AI for confirmation when an API key is available.
    """
    amount_variance_threshold = getattr(settings, 'RECURRING_AMOUNT_VARIANCE', 0.20)
    cv_threshold = getattr(settings, 'RECURRING_CV_THRESHOLD', 0.30)
    min_transactions = getattr(settings, 'RECURRING_MIN_TRANSACTIONS', 3)

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
    confirmed_groups = []   # (vendor, currency, txs, group_id) — clearly recurring
    ambiguous_groups = []   # (vendor, currency, txs, period, cv, amount_var)

    for (vendor, currency), vendor_txs in by_vendor.items():
        if len(vendor_txs) < min_transactions:
            continue

        # Sort by date
        vendor_txs.sort(key=lambda t: t.date)

        # Compute intervals between consecutive transactions
        intervals = []
        for i in range(1, len(vendor_txs)):
            delta = (vendor_txs[i].date - vendor_txs[i - 1].date).days
            if delta > 0:
                intervals.append(delta)

        if not intervals:
            continue

        # Check if intervals are regular
        avg_interval = sum(intervals) / len(intervals)
        if avg_interval == 0:
            continue
        std = (sum((i - avg_interval) ** 2 for i in intervals) / len(intervals)) ** 0.5
        cv = std / avg_interval

        period = _detect_period(intervals, cv_threshold)
        if not period:
            continue

        # Check amount similarity
        amounts = [abs(float(t.value)) for t in vendor_txs]
        avg_amount = sum(amounts) / len(amounts)
        if avg_amount == 0:
            continue
        amount_variance = max(abs(a - avg_amount) / avg_amount for a in amounts)
        if amount_variance > amount_variance_threshold:
            continue

        group_id = f'{slugify(vendor)}_{period}_{currency.lower()}'

        # Determine if this group is ambiguous
        is_ambiguous = (
            len(vendor_txs) == min_transactions
            or (0.2 <= cv <= cv_threshold)
            or (0.15 <= amount_variance <= amount_variance_threshold)
        )

        if is_ambiguous:
            ambiguous_groups.append((vendor, currency, vendor_txs, period, cv, amount_variance))
        else:
            confirmed_groups.append((vendor, currency, vendor_txs, group_id, avg_amount))

    # Mark confirmed groups as recurring
    for vendor, currency, vendor_txs, group_id, avg_amount in confirmed_groups:
        for tx in vendor_txs:
            tx.is_recurring = True
            tx.recurring_group_id = group_id

        BankTransaction.objects.bulk_update(
            vendor_txs, ['is_recurring', 'recurring_group_id'], batch_size=100
        )

        recurring_groups += 1
        recurring_txs += len(vendor_txs)
        logger.info(
            '[Recurring] Detected: %s (%s, %d txs, ~%.2f %s)',
            vendor, group_id.split('_')[1] if '_' in group_id else group_id,
            len(vendor_txs), avg_amount, currency,
        )

    # AI confirmation for ambiguous cases
    if ambiguous_groups:
        api_key = os.getenv('ANTHROPIC_API_KEY', '')
        ai_decisions = _ai_confirm_recurring(ambiguous_groups, api_key) if api_key else {}

        for vendor, currency, vendor_txs, period, cv, amount_variance in ambiguous_groups:
            # If AI gave a decision, use it; otherwise default to statistical result (recurring)
            ai_says = ai_decisions.get(vendor)
            if ai_says is False:
                logger.info(
                    '[Recurring] AI rejected ambiguous group: %s (%s, cv=%.3f, var=%.3f)',
                    vendor, period, cv, amount_variance,
                )
                continue

            group_id = f'{slugify(vendor)}_{period}_{currency.lower()}'
            amounts = [abs(float(t.value)) for t in vendor_txs]
            avg_amount = sum(amounts) / len(amounts)

            for tx in vendor_txs:
                tx.is_recurring = True
                tx.recurring_group_id = group_id

            BankTransaction.objects.bulk_update(
                vendor_txs, ['is_recurring', 'recurring_group_id'], batch_size=100
            )

            recurring_groups += 1
            recurring_txs += len(vendor_txs)
            source = 'AI-confirmed' if ai_says is True else 'statistical'
            logger.info(
                '[Recurring] Detected (%s): %s (%s, %d txs, ~%.2f %s)',
                source, vendor, period, len(vendor_txs), avg_amount, currency,
            )

    logger.info('[Recurring] %d groups, %d transactions', recurring_groups, recurring_txs)
    return {'recurring_groups': recurring_groups, 'recurring_transactions': recurring_txs}


def _ai_confirm_recurring(ambiguous_groups, api_key):
    """Ask AI to confirm/deny ambiguous recurring transaction groups."""
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    # Format groups for the AI
    groups_data = []
    for vendor, currency, txs, period, cv, amount_var in ambiguous_groups:
        groups_data.append({
            "vendor": vendor,
            "currency": currency,
            "period_detected": period,
            "cv": round(cv, 3),
            "amount_variance": round(amount_var, 3),
            "transactions": [
                {
                    "date": str(t.date),
                    "amount": float(t.value),
                    "wording": t.simplified_wording or t.original_wording or '',
                }
                for t in txs
            ]
        })

    if not groups_data:
        return {}

    prompt = (
        "Review these potentially recurring transaction groups. For each, decide if they are truly recurring "
        "(subscription, regular bill, membership) or just coincidental similar transactions.\n\n"
        "RECURRING indicators:\n"
        "- Subscription-like wording (Monthly, Plan, Premium, Membership, Abonnement)\n"
        "- Same service/vendor at regular intervals\n"
        "- Utility bills (electricity, internet, phone)\n\n"
        "NOT RECURRING indicators:\n"
        "- Order numbers that differ (Order #123, Order #456 = different purchases)\n"
        "- One-off purchases that happen to be similar amounts\n"
        "- Grocery store visits (same store, similar amounts, but not a subscription)\n\n"
        "<examples>\n"
        "<example>\n"
        "Input: {\"vendor\": \"netflix\", \"transactions\": [{\"date\": \"2026-01-15\", \"amount\": -13.49}, {\"date\": \"2026-02-15\", \"amount\": -13.49}, {\"date\": \"2026-03-15\", \"amount\": -13.49}]}\n"
        "Output: {\"vendor\": \"netflix\", \"is_recurring\": true, \"reason\": \"Same amount, monthly interval, streaming subscription\"}\n"
        "</example>\n"
        "<example>\n"
        "Input: {\"vendor\": \"monoprix\", \"transactions\": [{\"date\": \"2026-01-10\", \"amount\": -45.30}, {\"date\": \"2026-02-12\", \"amount\": -52.10}, {\"date\": \"2026-03-08\", \"amount\": -38.90}]}\n"
        "Output: {\"vendor\": \"monoprix\", \"is_recurring\": false, \"reason\": \"Grocery store visits with varying amounts - regular shopping habit, not a subscription\"}\n"
        "</example>\n"
        "</examples>\n\n"
        f"Groups to review:\n{json.dumps(groups_data, indent=2)}\n\n"
        "Return JSON: {\"decisions\": [{\"vendor\": \"...\", \"is_recurring\": true/false, \"reason\": \"...\"}]}\n"
        "No other text."
    )

    try:
        response = client.messages.create(
            model=getattr(settings, 'AI_MODEL_RECURRING', 'claude-haiku-4-5-20251001'),
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": {
                        "type": "object",
                        "properties": {
                            "decisions": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "vendor": {"type": "string"},
                                        "is_recurring": {"type": "boolean"},
                                        "reason": {"type": "string"}
                                    },
                                    "required": ["vendor", "is_recurring", "reason"],
                                    "additionalProperties": False
                                }
                            }
                        },
                        "required": ["decisions"],
                        "additionalProperties": False
                    }
                }
            },
        )

        text = response.content[0].text
        result = json.loads(text)
        decisions = result.get('decisions', [])
        return {d['vendor']: d['is_recurring'] for d in decisions if isinstance(d, dict)}
    except Exception as e:
        logger.warning('[Recurring] AI confirmation failed: %s, keeping statistical result', e)
        return {}


def _detect_period(intervals, cv_threshold=None):
    """Given list of day intervals, return period name or None."""
    if cv_threshold is None:
        cv_threshold = getattr(settings, 'RECURRING_CV_THRESHOLD', 0.30)
    if not intervals:
        return None
    avg = sum(intervals) / len(intervals)
    if avg == 0:
        return None
    std = (sum((i - avg) ** 2 for i in intervals) / len(intervals)) ** 0.5
    # Too much variance = not recurring
    if std / avg > cv_threshold:
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
