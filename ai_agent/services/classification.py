"""
AI-driven bank transaction classification.

Replaces hardcoded vendor_rules.py with AI that DECIDES classifications.
The regex rules and email context are pre-fetched Python-side and provided
to the AI in a single-shot API call with structured output.

Design principles (Anthropic best practices):
- One task per pass: classify transactions
- Small batches (20 txs): avoid hallucination
- Single-shot: pre-fetch all context, one API call per batch
- Worker + Verifier: independent verification pass
- Structured output: JSON schema enforced by the API
"""
import json
import logging
import os
from decimal import Decimal

import anthropic
from django.conf import settings
from django.utils import timezone

from banking.models import BankTransaction, TransactionMatch
from banking.services.vendor_rules import classify_wording  # fallback

logger = logging.getLogger(__name__)

CLASSIFICATION_BATCH_SIZE = 20
MODEL_CLASSIFICATION = getattr(settings, 'AI_MODEL_CLASSIFICATION', 'claude-sonnet-4-5-20250929')
MODEL_VERIFIER = getattr(settings, 'AI_MODEL_VERIFIER', 'claude-sonnet-4-5-20250929')


CLASSIFICATION_SYSTEM_PROMPT = (
    "<role>You are a French accounting expert classifying bank transactions for a small business (PME/startup).</role>\n\n"
    "<instructions>\n"
    "For each bank transaction, determine:\n"
    "1. expense_category: PCG (Plan Comptable General) code\n"
    "2. expense_category_label: human-readable category name\n"
    "3. business_personal: is this a business expense, personal, or unknown?\n"
    "4. tva_deductible: is TVA (VAT) deductible on this expense?\n"
    "5. vendor_type: what kind of vendor is this (saas, transport, food_delivery, groceries, etc.)\n"
    "6. confidence: how confident are you in this classification (0.0-1.0)\n\n"
    "CONTEXT PROVIDED:\n"
    "- rule_suggestion: existing vendor classification rules (if any match). Use as reference, not law.\n"
    "- email_context: linked email transaction data (vendor, description, items). Use for better decisions.\n\n"
    "KEY PRINCIPLES:\n"
    "- YOU decide. The rules are reference, not law. A 'GOOGLE' charge could be Cloud (business) or Play Store (personal).\n"
    "- Context matters: amount, date patterns, and email context can change the classification.\n"
    "- When unsure, set business_personal='unknown' and confidence lower.\n"
    "- TVA is deductible for most business expenses from French/EU vendors, NOT for personal expenses.\n"
    "- TVA is NOT deductible for non-EU vendors (US SaaS like GitHub, Stripe, etc.)\n"
    "- PCG codes: 606=achats, 613=locations, 615=services numeriques, 616=assurances, 625=deplacements/repas, "
    "626=telecom, 627=services bancaires, 628=abonnements, 791=salaire.\n\n"
    "<examples>\n"
    "<example>\n"
    'Input: {"wording": "GITHUB INC", "amount": -4.00, "currency": "USD"}\n'
    'Output: {"expense_category": "615", "expense_category_label": "Services numériques", '
    '"business_personal": "business", "tva_deductible": false, "vendor_type": "saas", '
    '"confidence": 0.95, "reasoning": "GitHub is a development SaaS. US vendor = no TVA déductible."}\n'
    "</example>\n"
    "<example>\n"
    'Input: {"wording": "UBER EATS", "amount": -25.50, "currency": "EUR"}\n'
    'Output: {"expense_category": "6257", "expense_category_label": "Frais de réception", '
    '"business_personal": "unknown", "tva_deductible": false, "vendor_type": "food_delivery", '
    '"confidence": 0.7, "reasoning": "Uber Eats could be business meal or personal. '
    'Cannot determine without more context. TVA not deductible until confirmed business."}\n'
    "</example>\n"
    "<example>\n"
    'Input: {"wording": "OVH SAS ROUBAIX", "amount": -14.39, "currency": "EUR"}\n'
    'Output: {"expense_category": "615", "expense_category_label": "Services numériques", '
    '"business_personal": "business", "tva_deductible": true, "vendor_type": "hosting", '
    '"confidence": 0.95, "reasoning": "OVH is a French hosting provider (SAS = French company). '
    'Server hosting for a startup = business. French vendor = TVA déductible."}\n'
    "</example>\n"
    "</examples>\n"
    "</instructions>"
)

CLASSIFICATION_VERIFIER_PROMPT = (
    "Review these bank transaction classifications. ONLY flag CLEAR errors.\n\n"
    "CHECK:\n"
    "- Is the PCG code appropriate for this type of expense?\n"
    "- Is business_personal correct given the vendor and amount?\n"
    "- Is tva_deductible consistent with business_personal? (personal = no TVA deduction)\n"
    "- Does the vendor_type make sense for the wording?\n\n"
    "BE CONSERVATIVE. Only correct if you are 100% certain.\n\n"
    "Classifications: {classifications}\n\n"
    "Return JSON: {{\"corrections\": [{{\"bank_transaction_id\": <id>, \"field\": \"<field>\", \"correct_value\": <value>, \"reason\": \"...\"}}]}} or {{\"corrections\": []}} if all correct.\n"
    "No other text."
)


def _handle_save_classifications(classifications, user):
    """Save AI classification results to bank transactions."""
    saved = 0
    for c in classifications:
        try:
            tx = BankTransaction.objects.get(id=c['bank_transaction_id'], user=user)
            tx.expense_category = c.get('expense_category', '')
            tx.expense_category_label = c.get('expense_category_label', '')
            tx.business_personal = c.get('business_personal', 'unknown')
            tx.tva_deductible = c.get('tva_deductible', False)
            tx.vendor_type = c.get('vendor_type', '')
            tx.enriched_at = timezone.now()
            tx.save(update_fields=[
                'expense_category', 'expense_category_label', 'business_personal',
                'tva_deductible', 'vendor_type', 'enriched_at',
            ])
            saved += 1
        except BankTransaction.DoesNotExist:
            logger.warning('[Classification] Bank transaction %d not found', c['bank_transaction_id'])
    return json.dumps({"saved": saved})


# ============================================================
# AI CLASSIFICATION ENGINE
# ============================================================

def _classify_batch_with_ai(batch_txs, user, api_key):
    """Classify a batch of bank transactions using a single-shot API call."""
    client = anthropic.Anthropic(api_key=api_key)

    # Pre-fetch all context Python-side
    tx_data = []
    for tx in batch_txs:
        wording = tx.simplified_wording or tx.original_wording or ''

        # Lookup vendor rules
        rule_match = classify_wording(wording)

        # Lookup email context
        email_ctx = None
        try:
            match = TransactionMatch.objects.select_related(
                'email_transaction', 'email_transaction__email'
            ).get(bank_transaction_id=tx.id)
            etx = match.email_transaction
            email_ctx = {
                "vendor": etx.vendor_name,
                "description": etx.description,
                "amount": float(etx.amount) if etx.amount else None,
                "type": etx.type,
                "email_subject": etx.email.subject if etx.email else None,
            }
        except TransactionMatch.DoesNotExist:
            pass

        tx_data.append({
            "id": tx.id,
            "wording": wording,
            "amount": float(tx.value) if tx.value else None,
            "date": str(tx.date) if tx.date else None,
            "currency": tx.account.currency if tx.account else 'EUR',
            "rule_suggestion": rule_match,
            "email_context": email_ctx,
        })

    # Single API call with structured output
    response = client.messages.create(
        model=MODEL_CLASSIFICATION,
        max_tokens=4096,
        system=[{
            "type": "text",
            "text": CLASSIFICATION_SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }],
        messages=[{"role": "user", "content": f"Classify these {len(tx_data)} bank transactions:\n{json.dumps(tx_data, indent=2)}"}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "classifications": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "bank_transaction_id": {"type": "integer"},
                                    "expense_category": {"type": "string"},
                                    "expense_category_label": {"type": "string"},
                                    "business_personal": {"type": "string", "enum": ["business", "personal", "unknown"]},
                                    "tva_deductible": {"type": "boolean"},
                                    "vendor_type": {"type": "string"},
                                    "confidence": {"type": "number"},
                                    "reasoning": {"type": "string"}
                                },
                                "required": ["bank_transaction_id", "expense_category", "expense_category_label", "business_personal", "tva_deductible", "vendor_type", "confidence"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["classifications"],
                    "additionalProperties": False
                }
            }
        },
    )

    # Parse and save
    result = json.loads(response.content[0].text)
    classifications = result.get('classifications', [])
    _handle_save_classifications(classifications, user)

    # Track ambiguous classifications
    confidence_threshold = getattr(settings, 'AI_CLASSIFICATION_CONFIDENCE_THRESHOLD', 0.7)
    ambiguous_ids = [
        c['bank_transaction_id'] for c in classifications
        if c.get('confidence', 1.0) < confidence_threshold
    ]

    return len(tx_data), ambiguous_ids


def _run_verifier(batch_txs, user, api_key):
    """Run independent verifier on classifications."""
    client = anthropic.Anthropic(api_key=api_key)

    # Get current classifications for the batch
    classifications = []
    for tx in batch_txs:
        tx.refresh_from_db()
        classifications.append({
            "bank_transaction_id": tx.id,
            "wording": tx.simplified_wording or tx.original_wording or '',
            "amount": float(tx.value) if tx.value else None,
            "expense_category": tx.expense_category or '',
            "expense_category_label": tx.expense_category_label or '',
            "business_personal": tx.business_personal or 'unknown',
            "tva_deductible": tx.tva_deductible,
            "vendor_type": tx.vendor_type or '',
        })

    prompt = CLASSIFICATION_VERIFIER_PROMPT.format(
        classifications=json.dumps(classifications, indent=2)
    )

    response = client.messages.create(
        model=MODEL_VERIFIER,
        max_tokens=2048,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "format": {
                "type": "json_schema",
                "schema": {
                    "type": "object",
                    "properties": {
                        "corrections": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "bank_transaction_id": {"type": "integer"},
                                    "field": {"type": "string"},
                                    "correct_value": {},
                                    "reason": {"type": "string"}
                                },
                                "required": ["bank_transaction_id", "field", "correct_value", "reason"],
                                "additionalProperties": False
                            }
                        }
                    },
                    "required": ["corrections"],
                    "additionalProperties": False
                }
            }
        },
    )

    text = response.content[0].text
    try:
        result = json.loads(text)
        corrections = result.get('corrections', [])
        if corrections:
            for corr in corrections:
                try:
                    tx = BankTransaction.objects.get(
                        id=corr['bank_transaction_id'], user=user
                    )
                    field = corr['field']
                    if field in ('expense_category', 'expense_category_label',
                                 'business_personal', 'vendor_type'):
                        setattr(tx, field, corr['correct_value'])
                    elif field == 'tva_deductible':
                        tx.tva_deductible = bool(corr['correct_value'])
                    tx.save(update_fields=[field])
                    logger.info(
                        '[Classification-Verifier] Corrected tx %d: %s -> %s (%s)',
                        tx.id, field, corr['correct_value'], corr.get('reason', '')
                    )
                except (BankTransaction.DoesNotExist, KeyError) as e:
                    logger.warning('[Classification-Verifier] Error applying correction: %s', e)
    except (json.JSONDecodeError, TypeError):
        pass  # No corrections or invalid response


def _fallback_classify(batch_txs, user):
    """Fallback: use vendor_rules.py regex when API is unavailable."""
    enriched = 0
    for tx in batch_txs:
        wording = tx.simplified_wording or tx.original_wording or ''
        result = classify_wording(wording)
        if result:
            tx.expense_category = result['category_pcg']
            tx.expense_category_label = result['category_label']
            tx.business_personal = result['business_personal']
            tx.tva_deductible = result['tva_deductible']
            tx.vendor_type = result['vendor_type']
            enriched += 1
        tx.enriched_at = timezone.now()

    BankTransaction.objects.bulk_update(
        batch_txs,
        ['expense_category', 'expense_category_label', 'business_personal',
         'tva_deductible', 'vendor_type', 'enriched_at'],
        batch_size=100
    )
    return enriched


# ============================================================
# EXTENDED THINKING — AMBIGUOUS RECLASSIFICATION
# ============================================================

def _reclassify_with_thinking(ambiguous_ids, user, api_key):
    """Reclassify ambiguous transactions using extended thinking for deeper reasoning."""
    if not ambiguous_ids:
        return 0

    client = anthropic.Anthropic(api_key=api_key)

    txs = list(BankTransaction.objects.filter(
        id__in=ambiguous_ids, user=user
    ).select_related('account'))

    if not txs:
        return 0

    # Pre-fetch context (same as single-shot)
    tx_data = []
    for tx in txs:
        wording = tx.simplified_wording or tx.original_wording or ''
        rule_match = classify_wording(wording)

        email_ctx = None
        try:
            match = TransactionMatch.objects.select_related(
                'email_transaction', 'email_transaction__email'
            ).get(bank_transaction_id=tx.id)
            etx = match.email_transaction
            email_ctx = {
                "vendor": etx.vendor_name,
                "description": etx.description,
                "amount": float(etx.amount) if etx.amount else None,
                "type": etx.type,
                "email_subject": etx.email.subject if etx.email else None,
            }
        except TransactionMatch.DoesNotExist:
            pass

        tx_data.append({
            "id": tx.id,
            "wording": wording,
            "amount": float(tx.value) if tx.value else None,
            "date": str(tx.date) if tx.date else None,
            "currency": tx.account.currency if tx.account else 'EUR',
            "rule_suggestion": rule_match,
            "email_context": email_ctx,
        })

    try:
        # NOTE: extended thinking is incompatible with output_config (structured output)
        # and temperature cannot be set. We ask for JSON in the prompt and parse manually.
        response = client.messages.create(
            model=MODEL_CLASSIFICATION,
            max_tokens=8192,
            thinking={
                "type": "enabled",
                "budget_tokens": 3000,
            },
            system=[{
                "type": "text",
                "text": CLASSIFICATION_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"}
            }],
            messages=[{
                "role": "user",
                "content": (
                    f"These {len(tx_data)} transactions were classified with LOW confidence. "
                    f"Think carefully about each one. Consider the business context of a French startup.\n\n"
                    f"Transactions:\n{json.dumps(tx_data, indent=2)}\n\n"
                    f"Return your classifications as JSON: "
                    f"{{\"classifications\": [{{\"bank_transaction_id\": <id>, \"expense_category\": \"...\", "
                    f"\"expense_category_label\": \"...\", \"business_personal\": \"business|personal|unknown\", "
                    f"\"tva_deductible\": true/false, \"vendor_type\": \"...\", \"confidence\": 0.0-1.0, "
                    f"\"reasoning\": \"...\"}}]}}\n"
                    f"Return ONLY the JSON object, no other text."
                )
            }],
        )

        # Find the text block (skip thinking blocks)
        text_content = None
        for block in response.content:
            if hasattr(block, 'text'):
                text_content = block.text
                break

        if text_content:
            result = json.loads(text_content)
            classifications = result.get('classifications', [])
            _handle_save_classifications(classifications, user)
            logger.info(
                '[Classification-Thinking] Reclassified %d ambiguous transactions',
                len(classifications)
            )
            return len(classifications)

    except Exception as e:
        logger.warning('[Classification-Thinking] Extended thinking failed: %s', e)

    return 0


# ============================================================
# MAIN ENTRY POINT
# ============================================================

def classify_bank_transactions(user, force=False):
    """
    Classify bank transactions using AI (with regex rules as tool reference).
    Falls back to regex-only classification if API is unavailable.

    Returns stats dict.
    """
    api_key = os.environ.get('ANTHROPIC_API_KEY')

    if force:
        txs = list(BankTransaction.objects.filter(user=user).select_related('account'))
    else:
        txs = list(BankTransaction.objects.filter(
            user=user, enriched_at__isnull=True
        ).select_related('account'))

    if not txs:
        return {'classified': 0, 'total': 0, 'method': 'none'}

    logger.info('[Classification] Starting AI classification for %d transactions', len(txs))

    # Try AI classification first
    if api_key:
        try:
            classified = 0
            all_ambiguous_ids = []
            for i in range(0, len(txs), CLASSIFICATION_BATCH_SIZE):
                batch = txs[i:i + CLASSIFICATION_BATCH_SIZE]
                count, ambiguous_ids = _classify_batch_with_ai(batch, user, api_key)
                classified += count
                all_ambiguous_ids.extend(ambiguous_ids)

                # Run verifier on this batch
                _run_verifier(batch, user, api_key)

            # Second pass: reclassify ambiguous cases with extended thinking
            confidence_threshold = getattr(settings, 'AI_CLASSIFICATION_CONFIDENCE_THRESHOLD', 0.7)
            if all_ambiguous_ids:
                logger.info(
                    '[Classification] %d ambiguous transactions (confidence < %.1f), '
                    'reclassifying with extended thinking',
                    len(all_ambiguous_ids), confidence_threshold
                )
                reclassified = _reclassify_with_thinking(all_ambiguous_ids, user, api_key)
                classified += reclassified

            logger.info('[Classification] AI classified %d transactions', classified)
            return {'classified': classified, 'total': len(txs), 'method': 'ai'}

        except anthropic.APIError as e:
            logger.warning('[Classification] API error, falling back to rules: %s', e)
        except Exception as e:
            logger.error('[Classification] Unexpected error, falling back to rules: %s', e)

    # Fallback to regex rules
    logger.info('[Classification] Using regex fallback')
    enriched = _fallback_classify(txs, user)
    return {'classified': enriched, 'total': len(txs), 'method': 'regex_fallback'}
