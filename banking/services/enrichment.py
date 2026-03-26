"""Enrich bank transactions with categories, business/personal, vendor type, and recurring detection."""
import logging
from django.utils import timezone
from banking.models import BankTransaction
from banking.services.vendor_rules import classify_wording
from banking.services.recurring import detect_recurring

logger = logging.getLogger(__name__)


def enrich_transactions(user, force=False):
    """
    Enrich bank transactions with expense category, business/personal, TVA, vendor type.
    Also runs recurring detection.
    Returns stats dict.
    """
    if force:
        txs = BankTransaction.objects.filter(user=user)
    else:
        txs = BankTransaction.objects.filter(user=user, enriched_at__isnull=True)

    enriched = 0
    unclassified = 0

    to_update = []
    for tx in txs:
        wording = tx.simplified_wording or tx.original_wording or ''
        result = classify_wording(wording)

        if result:
            tx.expense_category = result['category_pcg']
            tx.expense_category_label = result['category_label']
            tx.business_personal = result['business_personal']
            tx.tva_deductible = result['tva_deductible']
            tx.vendor_type = result['vendor_type']
            enriched += 1
        else:
            unclassified += 1

        tx.enriched_at = timezone.now()
        to_update.append(tx)

    if to_update:
        BankTransaction.objects.bulk_update(
            to_update,
            ['expense_category', 'expense_category_label', 'business_personal',
             'tva_deductible', 'vendor_type', 'enriched_at'],
            batch_size=100
        )

    logger.info('[Enrichment] %d enriched, %d unclassified out of %d', enriched, unclassified, len(to_update))

    # Run recurring detection
    recurring_stats = detect_recurring(user)

    return {
        'enriched': enriched,
        'unclassified': unclassified,
        'total': len(to_update),
        **recurring_stats,
    }
