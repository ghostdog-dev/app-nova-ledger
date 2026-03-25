import logging
import re
from datetime import timedelta

from emails.models import Transaction

logger = logging.getLogger(__name__)

# Type specificity ranking: lower index = more specific
TYPE_PRIORITY = ['order', 'receipt', 'invoice', 'payment', 'shipping', 'subscription', 'refund', 'other']


def _normalize_vendor(name):
    """Normalize vendor name for grouping: lowercase, strip suffixes, punctuation."""
    if not name:
        return ''
    name = name.strip().lower()
    # Strip common corporate suffixes
    name = re.sub(
        r'\b(pbc\.?|inc\.?|ltd\.?|llc\.?|sas\.?|sa\.?|gmbh\.?|co\.?|corp\.?|limited|pty\.?)\s*$',
        '', name, flags=re.IGNORECASE,
    )
    # Strip commas and extra whitespace
    name = name.replace(',', '')
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _pick_best_type(type_a, type_b):
    """Return the more specific transaction type."""
    idx_a = TYPE_PRIORITY.index(type_a) if type_a in TYPE_PRIORITY else len(TYPE_PRIORITY)
    idx_b = TYPE_PRIORITY.index(type_b) if type_b in TYPE_PRIORITY else len(TYPE_PRIORITY)
    return type_a if idx_a <= idx_b else type_b


def _data_richness(tx):
    """Score how much data a transaction has (more = better primary candidate)."""
    score = 0
    if tx.amount is not None:
        score += 3
    if tx.transaction_date:
        score += 2
    if tx.order_number:
        score += 1
    if tx.invoice_number:
        score += 1
    if tx.description:
        score += 1
    if tx.vendor_name:
        score += 1
    return score


def _merge_pair(primary, secondary, reason):
    """
    Merge secondary into primary, delete secondary, return True.
    """
    logger.info(f'Merged transaction {secondary.id} into {primary.id}: {reason}')

    # Best amount: non-null wins, then highest
    if primary.amount is None and secondary.amount is not None:
        primary.amount = secondary.amount
    elif primary.amount is not None and secondary.amount is not None:
        primary.amount = max(primary.amount, secondary.amount)

    # Most specific type
    primary.type = _pick_best_type(primary.type, secondary.type)

    # Combine descriptions if different
    if secondary.description and secondary.description != primary.description:
        if primary.description:
            primary.description = f'{primary.description} | {secondary.description}'
        else:
            primary.description = secondary.description

    # Best order_number / invoice_number (non-empty wins)
    if not primary.order_number and secondary.order_number:
        primary.order_number = secondary.order_number
    if not primary.invoice_number and secondary.invoice_number:
        primary.invoice_number = secondary.invoice_number

    # Best date (non-null wins)
    if not primary.transaction_date and secondary.transaction_date:
        primary.transaction_date = secondary.transaction_date

    # Best currency
    if primary.currency == 'EUR' and secondary.currency and secondary.currency != 'EUR':
        primary.currency = secondary.currency

    # Highest confidence
    primary.confidence = max(primary.confidence, secondary.confidence)

    # Status: complete if we have vendor + amount + date
    if primary.vendor_name and primary.amount is not None and primary.transaction_date:
        primary.status = 'complete'
    else:
        primary.status = 'partial'

    # Reassign emails from secondary to primary
    # The Transaction model has a FK to Email, but one email can have multiple transactions.
    # If secondary has an email that primary doesn't, link it. Also reassign any
    # other transactions that pointed to secondary's email (shouldn't happen, but safe).
    if secondary.email and not primary.email:
        primary.email = secondary.email

    primary.save()

    # Delete the secondary
    secondary.delete()

    return True


def merge_related_transactions(user):
    """
    Post-processing: merge duplicate/fragmented transactions for a user.
    Returns {"merged": N, "remaining": M}.
    Safe to run multiple times (idempotent).
    """
    merged_count = 0

    # We'll iterate in passes until no more merges happen (handles chains).
    # In practice 1-2 passes suffice.
    max_passes = 5
    for pass_num in range(max_passes):
        merges_this_pass = 0

        transactions = list(Transaction.objects.filter(user=user).order_by('id'))
        if not transactions:
            break

        # Group by normalized vendor name
        groups = {}
        for tx in transactions:
            key = _normalize_vendor(tx.vendor_name)
            if key:
                groups.setdefault(key, []).append(tx)

        # Track IDs that have been deleted this pass
        deleted_ids = set()

        for vendor_key, txs in groups.items():
            if len(txs) < 2:
                continue

            # Rule 1: Same order_number (non-empty) + same vendor -> merge
            order_groups = {}
            for tx in txs:
                if tx.id in deleted_ids:
                    continue
                if tx.order_number:
                    order_groups.setdefault(tx.order_number, []).append(tx)

            for order_num, group in order_groups.items():
                if len(group) < 2:
                    continue
                # Sort by richness descending, pick best as primary
                group.sort(key=lambda t: _data_richness(t), reverse=True)
                primary = group[0]
                for secondary in group[1:]:
                    if secondary.id in deleted_ids:
                        continue
                    _merge_pair(primary, secondary, f'same order_number "{order_num}"')
                    deleted_ids.add(secondary.id)
                    merges_this_pass += 1

            # Rebuild active list for remaining rules
            active = [tx for tx in txs if tx.id not in deleted_ids]

            # Rule 2: Same vendor + same amount + same date -> merge (likely duplicate)
            seen_amt_date = {}
            for tx in active:
                if tx.id in deleted_ids:
                    continue
                if tx.amount is not None and tx.transaction_date:
                    key = (str(tx.amount), tx.transaction_date)
                    if key in seen_amt_date:
                        primary_tx = seen_amt_date[key]
                        if primary_tx.id in deleted_ids:
                            seen_amt_date[key] = tx
                            continue
                        # Pick the richer one as primary
                        if _data_richness(tx) > _data_richness(primary_tx):
                            primary_tx, tx = tx, primary_tx
                            seen_amt_date[key] = primary_tx
                        _merge_pair(primary_tx, tx, f'same amount ({tx.amount}) + same date ({tx.transaction_date})')
                        deleted_ids.add(tx.id)
                        merges_this_pass += 1
                    else:
                        seen_amt_date[key] = tx

            # Rebuild active list
            active = [tx for tx in txs if tx.id not in deleted_ids]

            # Rule 3: One has amount, other doesn't + dates within 2 days -> merge (shipping + order)
            with_amount = [tx for tx in active if tx.id not in deleted_ids and tx.amount is not None and tx.transaction_date]
            without_amount = [tx for tx in active if tx.id not in deleted_ids and tx.amount is None and tx.transaction_date]

            for no_amt in without_amount:
                if no_amt.id in deleted_ids:
                    continue
                for has_amt in with_amount:
                    if has_amt.id in deleted_ids:
                        continue
                    delta = abs((has_amt.transaction_date - no_amt.transaction_date).days)
                    if delta <= 2:
                        _merge_pair(has_amt, no_amt, f'one has amount, other does not, dates {delta}d apart')
                        deleted_ids.add(no_amt.id)
                        merges_this_pass += 1
                        break  # This no_amt is consumed

            # Rebuild active list
            active = [tx for tx in txs if tx.id not in deleted_ids]

            # Rule 4: Same vendor + same date + both have no amount -> merge (exact duplicate)
            seen_no_amt_date = {}
            for tx in active:
                if tx.id in deleted_ids:
                    continue
                if tx.amount is None and tx.transaction_date:
                    key = tx.transaction_date
                    if key in seen_no_amt_date:
                        primary_tx = seen_no_amt_date[key]
                        if primary_tx.id in deleted_ids:
                            seen_no_amt_date[key] = tx
                            continue
                        if _data_richness(tx) > _data_richness(primary_tx):
                            primary_tx, tx = tx, primary_tx
                            seen_no_amt_date[key] = primary_tx
                        _merge_pair(primary_tx, tx, f'both no amount + same date ({tx.transaction_date})')
                        deleted_ids.add(tx.id)
                        merges_this_pass += 1
                    else:
                        seen_no_amt_date[key] = tx

        merged_count += merges_this_pass

        if merges_this_pass == 0:
            break

        logger.info(f'Merge pass {pass_num + 1}: {merges_this_pass} merges')

    remaining = Transaction.objects.filter(user=user).count()
    logger.info(f'Merge complete: {merged_count} merged, {remaining} remaining')

    return {"merged": merged_count, "remaining": remaining}
