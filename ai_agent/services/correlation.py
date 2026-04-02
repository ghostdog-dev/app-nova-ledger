"""
Bank-to-email transaction correlation.
Purely deterministic — no LLM needed.
"""
import logging
import re
from datetime import timedelta
from decimal import Decimal

from django.conf import settings

from banking.models import BankTransaction, ProviderMatch, TransactionMatch
from banking.services.utils import normalize_vendor
from emails.models import Transaction

logger = logging.getLogger(__name__)

DATE_TOLERANCE_DAYS = 3



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
    bank_vendor = normalize_vendor(btx.simplified_wording or btx.original_wording)
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
            'normalized_vendor': normalize_vendor(etx.vendor_name),
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


def _provider_dates_match(provider_date, email_date, tolerance_days=DATE_TOLERANCE_DAYS):
    """Check if a provider date and email date are within tolerance."""
    if not provider_date or not email_date:
        return False
    # provider_date may be a datetime — extract .date() if needed
    p_date = provider_date.date() if hasattr(provider_date, 'date') else provider_date
    e_date = email_date.date() if hasattr(email_date, 'date') else email_date
    delta = abs((p_date - e_date).days)
    return delta <= tolerance_days


def _find_provider_email_match(provider_amount, provider_currency, provider_date,
                                provider_description, email_candidates):
    """
    Find the best email transaction match for a provider transaction.
    Returns {tx, confidence, method} or None.
    """
    provider_vendor = normalize_vendor(provider_description)
    candidates = []

    for ec in email_candidates:
        etx = ec['tx']
        e_amount = ec['abs_amount']
        e_currency = etx.currency or ''
        e_vendor = ec['normalized_vendor']
        e_date = etx.transaction_date

        # Currency check
        if provider_currency and e_currency and provider_currency.upper() != e_currency.upper():
            continue

        # Amount must match exactly
        if abs(provider_amount) != e_amount:
            continue

        # Exact amount + vendor fuzzy + date match
        if _vendors_match_exact(provider_vendor, e_vendor):
            if _provider_dates_match(provider_date, e_date, tolerance_days=0):
                candidates.append({'tx': etx, 'confidence': 0.95, 'method': 'exact'})
                continue

        if _vendors_match_fuzzy(provider_vendor, e_vendor):
            if _provider_dates_match(provider_date, e_date, tolerance_days=0):
                candidates.append({'tx': etx, 'confidence': 0.85, 'method': 'fuzzy_vendor'})
                continue

        # Amount + date within tolerance (no vendor match needed — provider is authoritative)
        if _provider_dates_match(provider_date, e_date, tolerance_days=DATE_TOLERANCE_DAYS):
            if _vendors_match_exact(provider_vendor, e_vendor) or _vendors_match_fuzzy(provider_vendor, e_vendor):
                candidates.append({'tx': etx, 'confidence': 0.80, 'method': 'date_offset_vendor'})
                continue
            # Amount-only match with date tolerance (lower confidence)
            candidates.append({'tx': etx, 'confidence': 0.70, 'method': 'amount_date'})
            continue

        # Fallback: exact amount + vendor match, wider date tolerance (providers are authoritative)
        if _provider_dates_match(provider_date, e_date, tolerance_days=14):
            if _vendors_match_exact(provider_vendor, e_vendor) or _vendors_match_fuzzy(provider_vendor, e_vendor):
                candidates.append({'tx': etx, 'confidence': 0.65, 'method': 'amount_vendor_wide'})
                continue
            # Amount-only match with wide date tolerance (lowest confidence)
            if e_amount == abs(provider_amount):
                candidates.append({'tx': etx, 'confidence': 0.55, 'method': 'amount_only'})
                continue

    if not candidates:
        return None

    candidates.sort(key=lambda c: (-c['confidence'], -c['tx'].confidence))
    return candidates[0]


def correlate_providers(user):
    """
    Match provider transactions (Stripe, PayPal, Mollie) to email-extracted transactions.
    Also matches Stripe payouts to bank credits.
    Returns stats dict.
    """
    logger.info('[Correlation-Provider] Starting provider correlation for user %s', user.email)

    # Get email transactions (with amount)
    email_txns = Transaction.objects.filter(user=user, amount__isnull=False)
    if not email_txns.exists():
        logger.info('[Correlation-Provider] No email transactions to correlate')
        return {
            'provider_stripe_matched': 0, 'provider_paypal_matched': 0,
            'provider_mollie_matched': 0, 'provider_payout_matched': 0,
        }

    # Pre-compute email candidates
    email_candidates = []
    for etx in email_txns:
        email_candidates.append({
            'tx': etx,
            'normalized_vendor': normalize_vendor(etx.vendor_name),
            'abs_amount': abs(etx.amount),
        })

    # Skip already-matched provider transaction IDs
    already_matched = set(
        ProviderMatch.objects.filter(user=user)
        .values_list('provider_transaction_id', flat=True)
    )

    stats = {
        'provider_stripe_matched': 0,
        'provider_paypal_matched': 0,
        'provider_mollie_matched': 0,
        'provider_payout_matched': 0,
    }

    # --- Stripe charges (succeeded) ---
    try:
        from stripe_provider.models import StripeCharge
        stripe_charges = StripeCharge.objects.filter(
            user=user, status='succeeded'
        ).exclude(stripe_id__in=already_matched)

        for sc in stripe_charges:
            # Stripe amounts are in cents — convert to decimal
            amount_decimal = Decimal(str(sc.amount)) / Decimal('100')
            best = _find_provider_email_match(
                provider_amount=amount_decimal,
                provider_currency=sc.currency,
                provider_date=sc.created_at_stripe,
                provider_description=sc.description or sc.statement_descriptor or '',
                email_candidates=email_candidates,
            )
            if best:
                ProviderMatch.objects.update_or_create(
                    provider='stripe',
                    provider_transaction_id=sc.stripe_id,
                    defaults={
                        'user': user,
                        'email_transaction': best['tx'],
                        'provider_amount': amount_decimal,
                        'provider_currency': sc.currency.upper(),
                        'confidence': best['confidence'],
                        'match_method': best['method'],
                    }
                )
                logger.info(
                    '[Correlation-Provider] Stripe match: %s (%.2f %s) <> email %d (%s) | method=%s conf=%.2f',
                    sc.stripe_id, amount_decimal, sc.currency,
                    best['tx'].id, best['tx'].vendor_name,
                    best['method'], best['confidence'],
                )
                stats['provider_stripe_matched'] += 1
    except ImportError:
        logger.debug('[Correlation-Provider] stripe_provider not installed, skipping')

    # --- PayPal transactions (completed, S status) ---
    try:
        from paypal_provider.models import PayPalTransaction
        paypal_txns = PayPalTransaction.objects.filter(
            user=user
        ).exclude(paypal_id__in=already_matched)

        for pt in paypal_txns:
            best = _find_provider_email_match(
                provider_amount=pt.amount,
                provider_currency=pt.currency,
                provider_date=pt.initiation_date,
                provider_description=pt.description or '',
                email_candidates=email_candidates,
            )
            if best:
                ProviderMatch.objects.update_or_create(
                    provider='paypal',
                    provider_transaction_id=pt.paypal_id,
                    defaults={
                        'user': user,
                        'email_transaction': best['tx'],
                        'provider_amount': abs(pt.amount),
                        'provider_currency': pt.currency.upper(),
                        'confidence': best['confidence'],
                        'match_method': best['method'],
                    }
                )
                logger.info(
                    '[Correlation-Provider] PayPal match: %s (%.2f %s) <> email %d (%s) | method=%s conf=%.2f',
                    pt.paypal_id, pt.amount, pt.currency,
                    best['tx'].id, best['tx'].vendor_name,
                    best['method'], best['confidence'],
                )
                stats['provider_paypal_matched'] += 1
    except ImportError:
        logger.debug('[Correlation-Provider] paypal_provider not installed, skipping')

    # --- Mollie payments (paid status) ---
    try:
        from mollie_provider.models import MolliePayment
        mollie_payments = MolliePayment.objects.filter(
            user=user, status__in=['paid', 'open', 'authorized']
        ).exclude(mollie_id__in=already_matched)

        for mp in mollie_payments:
            best = _find_provider_email_match(
                provider_amount=mp.amount,
                provider_currency=mp.currency,
                provider_date=mp.paid_at or mp.created_at_mollie,
                provider_description=mp.description or '',
                email_candidates=email_candidates,
            )
            if best:
                ProviderMatch.objects.update_or_create(
                    provider='mollie',
                    provider_transaction_id=mp.mollie_id,
                    defaults={
                        'user': user,
                        'email_transaction': best['tx'],
                        'provider_amount': abs(mp.amount),
                        'provider_currency': mp.currency.upper(),
                        'confidence': best['confidence'],
                        'match_method': best['method'],
                    }
                )
                logger.info(
                    '[Correlation-Provider] Mollie match: %s (%.2f %s) <> email %d (%s) | method=%s conf=%.2f',
                    mp.mollie_id, mp.amount, mp.currency,
                    best['tx'].id, best['tx'].vendor_name,
                    best['method'], best['confidence'],
                )
                stats['provider_mollie_matched'] += 1
    except ImportError:
        logger.debug('[Correlation-Provider] mollie_provider not installed, skipping')

    # --- Stripe payouts -> Bank credits ---
    try:
        from stripe_provider.models import StripePayout
        stripe_payouts = StripePayout.objects.filter(
            user=user, status='paid'
        )

        # Get unmatched bank credits
        already_matched_bank_ids = set(
            TransactionMatch.objects.filter(user=user)
            .values_list('bank_transaction_id', flat=True)
        )
        bank_credits = BankTransaction.objects.filter(
            user=user, value__gt=0, coming=False
        ).exclude(id__in=already_matched_bank_ids).select_related('account')

        for sp in stripe_payouts:
            payout_amount = Decimal(str(sp.amount)) / Decimal('100')
            payout_date = sp.arrival_date  # DateField
            payout_currency = sp.currency

            for btx in bank_credits:
                bank_currency = btx.account.currency if btx.account else ''
                if bank_currency and payout_currency and bank_currency.upper() != payout_currency.upper():
                    continue
                if abs(btx.value) != payout_amount:
                    continue
                # Date match: arrival_date should be close to bank date
                if payout_date and btx.date:
                    delta = abs((btx.date - payout_date).days)
                    if delta <= DATE_TOLERANCE_DAYS:
                        # Store as a ProviderMatch linked to the bank transaction via description
                        # We use the payout stripe_id as provider_transaction_id
                        if sp.stripe_id not in already_matched:
                            # For payout<>bank matches, we don't have an email_transaction
                            # Log the match but skip ProviderMatch (it requires email_transaction FK)
                            logger.info(
                                '[Correlation-Provider] Stripe payout match: %s (%.2f %s) <> bank %d (%.2f) | delta=%d days',
                                sp.stripe_id, payout_amount, payout_currency,
                                btx.id, btx.value, delta,
                            )
                            stats['provider_payout_matched'] += 1
                            break  # one match per payout
    except ImportError:
        logger.debug('[Correlation-Provider] stripe_provider not installed, skipping payouts')

    logger.info(
        '[Correlation-Provider] Done: stripe=%d, paypal=%d, mollie=%d, payouts=%d',
        stats['provider_stripe_matched'], stats['provider_paypal_matched'],
        stats['provider_mollie_matched'], stats['provider_payout_matched'],
    )
    return stats
