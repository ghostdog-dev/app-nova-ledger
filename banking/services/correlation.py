"""
Bank-to-email transaction correlation.
Purely deterministic — no LLM needed.
"""
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings

from banking.models import BankTransaction, TransactionMatch
from emails.models import Transaction

logger = logging.getLogger(__name__)

DATE_TOLERANCE_DAYS = 3


def _normalize_vendor(name):
    """Normalize vendor name for comparison. Lowercase, strip suffixes, common bank prefixes."""
    if not name:
        return ''
    name = name.lower().strip()
    # Strip common bank label prefixes
    for prefix in ['cb*', 'cb ', 'carte ', 'paiement par carte ', 'prlv ', 'vir ', 'virement ']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    # Strip corporate suffixes
    name = re.sub(r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sa\.?|gmbh\.?|co\.?|corp\.?|limited|pty\.?)\s*$', '', name)
    # Strip city names at end (common pattern: "VENDOR PARIS", "VENDOR LYON 02")
    name = re.sub(r'\s+(paris|lyon|marseille|bordeaux|toulouse|nantes|lille|nice|strasbourg|montpellier)\s*\d*\s*$', '', name)
    # Strip trailing numbers/codes
    name = re.sub(r'\s+\d{2,}$', '', name)
    # Clean up
    name = name.strip(' ,.*')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _vendors_match_exact(bank_vendor, email_vendor):
    """Exact normalized vendor match."""
    return bank_vendor and email_vendor and bank_vendor == email_vendor


def _vendors_match_fuzzy(bank_vendor, email_vendor):
    """Fuzzy vendor match: substring containment or token overlap >= 50%."""
    if not bank_vendor or not email_vendor:
        return False
    # Substring check
    if email_vendor in bank_vendor or bank_vendor in email_vendor:
        return True
    # Token overlap (Jaccard)
    bank_tokens = set(bank_vendor.split())
    email_tokens = set(email_vendor.split())
    if not bank_tokens or not email_tokens:
        return False
    intersection = bank_tokens & email_tokens
    union = bank_tokens | email_tokens
    return len(intersection) / len(union) >= 0.5


def _amounts_match(bank_value, email_amount, bank_currency, email_currency):
    """Check if amounts match (bank is negative, email is positive)."""
    if bank_value is None or email_amount is None:
        return False
    if bank_currency and email_currency and bank_currency.upper() != email_currency.upper():
        return False
    return abs(bank_value) == abs(email_amount)


def _dates_match(bank_rdate, bank_date, email_date, tolerance_days=0):
    """Check if dates match within tolerance. Prefer rdate (card swipe date)."""
    if not email_date:
        return False
    bank_d = bank_rdate or bank_date
    if not bank_d:
        return False
    delta = abs((bank_d - email_date).days)
    return delta <= tolerance_days


def _find_best_match(btx, email_candidates):
    """
    Find the best email transaction match for a bank transaction.
    Returns {tx, confidence, method} or None.
    """
    bank_vendor = _normalize_vendor(btx.simplified_wording or btx.original_wording)
    bank_abs_value = abs(btx.value)
    bank_currency = btx.account.currency if btx.account else ''

    candidates = []

    for ec in email_candidates:
        etx = ec['tx']
        e_vendor = ec['normalized_vendor']
        e_amount = ec['abs_amount']
        e_currency = etx.currency or ''
        e_date = etx.transaction_date

        # Step 1: Reference match (invoice/order number in bank wording)
        bank_wording = (btx.original_wording or '').lower()
        if etx.invoice_number and etx.invoice_number.lower() in bank_wording:
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                candidates.append({'tx': etx, 'confidence': 0.95, 'method': 'reference', 'date_delta': 0})
                continue
        if etx.order_number and etx.order_number.lower() in bank_wording:
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                candidates.append({'tx': etx, 'confidence': 0.95, 'method': 'reference', 'date_delta': 0})
                continue

        # Step 2: Exact vendor + exact amount + exact date
        if _vendors_match_exact(bank_vendor, e_vendor):
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                if _dates_match(btx.rdate, btx.date, e_date, tolerance_days=0):
                    candidates.append({'tx': etx, 'confidence': 0.95, 'method': 'exact', 'date_delta': 0})
                    continue

        # Step 3: Fuzzy vendor + exact amount + exact date
        if _vendors_match_fuzzy(bank_vendor, e_vendor):
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                if _dates_match(btx.rdate, btx.date, e_date, tolerance_days=0):
                    candidates.append({'tx': etx, 'confidence': 0.80, 'method': 'fuzzy_vendor', 'date_delta': 0})
                    continue

        # Step 4: Exact vendor + exact amount + date offset
        if _vendors_match_exact(bank_vendor, e_vendor):
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                if _dates_match(btx.rdate, btx.date, e_date, tolerance_days=DATE_TOLERANCE_DAYS):
                    bank_d = btx.rdate or btx.date
                    delta = abs((bank_d - e_date).days) if bank_d and e_date else 99
                    candidates.append({'tx': etx, 'confidence': 0.75, 'method': 'date_offset', 'date_delta': delta})
                    continue

        # Step 5: Fuzzy vendor + exact amount + date offset
        if _vendors_match_fuzzy(bank_vendor, e_vendor):
            if _amounts_match(btx.value, etx.amount, bank_currency, e_currency):
                if _dates_match(btx.rdate, btx.date, e_date, tolerance_days=DATE_TOLERANCE_DAYS):
                    bank_d = btx.rdate or btx.date
                    delta = abs((bank_d - e_date).days) if bank_d and e_date else 99
                    candidates.append({'tx': etx, 'confidence': 0.70, 'method': 'fuzzy_vendor', 'date_delta': delta})
                    continue

        # Step 6: Cross-currency match
        if btx.original_currency and btx.original_value is not None:
            if btx.original_currency.upper() == e_currency.upper():
                if abs(btx.original_value) == e_amount:
                    if _dates_match(btx.rdate, btx.date, e_date, tolerance_days=DATE_TOLERANCE_DAYS):
                        candidates.append({'tx': etx, 'confidence': 0.70, 'method': 'cross_currency', 'date_delta': 0})
                        continue

    if not candidates:
        return None

    # Pick best: highest confidence, then lowest date_delta, then highest email confidence
    candidates.sort(key=lambda c: (-c['confidence'], c['date_delta'], -c['tx'].confidence))
    return candidates[0]


def correlate_transactions(user):
    """
    Match bank debits to email-extracted transactions.
    Returns stats dict.
    """
    logger.info('[Correlation-Bank] Starting bank-email correlation for user %s', user.email)

    # Skip already-matched (auto or confirmed) and rejected bank txs
    already_matched_ids = set(
        TransactionMatch.objects.filter(user=user)
        .values_list('bank_transaction_id', flat=True)
    )

    # Get unmatched bank debits (negative value, posted)
    bank_txns = (
        BankTransaction.objects.filter(user=user, value__lt=0, coming=False)
        .exclude(id__in=already_matched_ids)
        .select_related('account')
    )

    # Get email transactions (complete, with amount)
    email_txns = Transaction.objects.filter(
        user=user, amount__isnull=False
    )

    if not bank_txns.exists() or not email_txns.exists():
        logger.info('[Correlation-Bank] Nothing to correlate (bank=%d, email=%d)', bank_txns.count(), email_txns.count())
        return {'bank_matched': 0, 'bank_unmatched': 0, 'bank_total': bank_txns.count()}

    # Pre-compute email candidates
    email_candidates = []
    for etx in email_txns:
        email_candidates.append({
            'tx': etx,
            'normalized_vendor': _normalize_vendor(etx.vendor_name),
            'abs_amount': abs(etx.amount),
        })

    matched = 0
    unmatched = 0

    for btx in bank_txns:
        best = _find_best_match(btx, email_candidates)
        if best:
            TransactionMatch.objects.update_or_create(
                bank_transaction=btx,
                defaults={
                    'email_transaction': best['tx'],
                    'user': user,
                    'confidence': best['confidence'],
                    'match_method': best['method'],
                    'status': TransactionMatch.Status.AUTO,
                }
            )
            logger.info(
                '[Correlation-Bank] Matched: bank %d (%s %.2f) <> email %d (%s) | method=%s confidence=%.2f',
                btx.id, btx.simplified_wording or btx.original_wording, btx.value,
                best['tx'].id, best['tx'].vendor_name,
                best['method'], best['confidence']
            )
            matched += 1
        else:
            unmatched += 1

    logger.info('[Correlation-Bank] Done: %d matched, %d unmatched', matched, unmatched)
    return {'bank_matched': matched, 'bank_unmatched': unmatched, 'bank_total': matched + unmatched}
