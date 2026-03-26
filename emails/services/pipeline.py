"""
Multi-pass email processing pipeline with worker/verifier pattern.

Architecture (4 passes):
  Pass 1 — TRIAGE:      classify emails as transactional or not (batches of 40, JSON)
  Pass 2 — EXTRACTION:  extract structured data (batches of 15, tool_use for body fetch)
  Pass 3 — CORRELATION: per-vendor group, suggest merges (JSON)
  Pass 4 — COMPUTATION: pure Python — compute derivable tax fields (no LLM)

Each of Passes 1-3 follows a WORKER + VERIFIER pattern:
  - Worker: does the main work (LLM call)
  - Verifier: independent LLM call reviewing worker output (fresh context, no self-confirmation)
"""

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import anthropic
from django.conf import settings

from emails.models import Email, Transaction
from emails.services.agent import (
    RateLimiter,
    _execute_get_email_body,
    _execute_mark_emails_processed,
    _execute_save_transactions,
    _normalize_vendor_name,
)
from emails.services.merge import merge_related_transactions
from emails.services.token_refresh import get_valid_token

logger = logging.getLogger(__name__)


# ============================================================
# CONSTANTS
# ============================================================

TRIAGE_BATCH_SIZE = settings.AI_TRIAGE_BATCH_SIZE
TRIAGE_MAX_CONCURRENT = settings.AI_TRIAGE_MAX_CONCURRENT

EXTRACTION_BATCH_SIZE = settings.AI_EXTRACTION_BATCH_SIZE
EXTRACTION_MAX_CONCURRENT = settings.AI_EXTRACTION_MAX_CONCURRENT

MAX_RETRIES = settings.AI_MAX_RETRIES
RETRY_BASE_DELAY = settings.AI_RETRY_BASE_DELAY

MODEL_TRIAGE = settings.AI_MODEL_TRIAGE
MODEL_EXTRACTION = settings.AI_MODEL_EXTRACTION
MODEL_CORRELATION = settings.AI_MODEL_CORRELATION


# ============================================================
# PROMPTS
# ============================================================

# --- Pass 1: Triage ---

TRIAGE_WORKER_PROMPT = (
    "For each email, answer: is this a real financial event "
    "(money charged, order placed, goods shipped, refund issued)?\n\n"
    "Transactional: invoice, receipt, order, payment (including failed), shipping, "
    "refund, cancellation of a paid order, subscription charge.\n\n"
    "Not transactional: newsletter, notification, conversation, security alert, "
    "marketing, welcome email without charge, free trial.\n\n"
    "Return JSON array: [{\"id\": <email_id>, \"transactional\": true/false}]\n"
    "No other text."
)

TRIAGE_VERIFIER_PROMPT = (
    "Review these triage decisions. ONLY correct CLEAR errors.\n\n"
    "SHOULD be transactional (true):\n"
    "- Order cancellation from a store (money was involved)\n"
    "- Failed payment notifications (a real charge was attempted)\n"
    "- Receipts, invoices, shipping confirmations\n\n"
    "SHOULD NOT be transactional (false) — DO NOT flip these to true:\n"
    "- Security alerts, new sign-in notifications, verification codes\n"
    "- Welcome emails, account creation, email verification\n"
    "- Marketplace messages that are just conversations (no money exchanged)\n"
    "- Azure/AWS/cloud account setup notifications\n"
    "- SSH key, password reset, 2FA notifications\n"
    "- Any email where NO money was charged or goods shipped\n\n"
    "Be CONSERVATIVE. Only correct if you are 100% certain the worker was wrong. "
    "When in doubt, do NOT correct.\n\n"
    "Decisions: {decisions}\n\n"
    "Return corrections: "
    "[{{\"id\": <email_id>, \"should_be\": true/false, \"reason\": \"...\"}}] "
    "or [] if all correct.\n"
    "No other text."
)

# --- Pass 2: Extraction ---

EXTRACTION_SYSTEM_PROMPT = (
    "<role>You are a financial data extractor for an accounting tool.</role>\n\n"
    "<instructions>\n"
    "For each email, extract ALL available structured data.\n\n"
    "Required: vendor_name, amount (total including tax), currency (ISO 4217), "
    "transaction_date (YYYY-MM-DD), type, description.\n\n"
    "Optional (extract if available):\n"
    "- invoice_number, order_number, payment_reference\n"
    "- payment_method (debit card, Mastercard, Visa, PayPal, bank transfer, Apple Pay, etc.)\n"
    "- amount_tax_excl (amount excluding tax), tax_amount, tax_rate (percentage, e.g. 20.0)\n"
    "- items: list of {name, quantity, unit_price}\n\n"
    "Computations (only when you have real numbers):\n"
    "- If total + tax_amount known: amount_tax_excl = total - tax_amount\n"
    "- If total + tax_rate known: tax_amount = total * rate / (100 + rate)\n"
    "- Round to 2 decimal places. NEVER guess tax rates.\n"
    "</instructions>\n\n"
    "<rules>\n"
    "- For orders, receipts, invoices: ALWAYS use get_email_body to get items and tax details\n"
    "- If snippet is empty: use get_email_body\n"
    "- Before saving, use the think tool to verify your extraction\n"
    "- Failed payments: type='payment', add 'FAILED' in description\n"
    "- NEVER invent data — if not found, leave null and set status='partial'\n"
    "- Currency: extract from email content. If not found, leave empty.\n"
    "- Set status='complete' if you have vendor + amount + date, otherwise 'partial'\n"
    "- confidence: 0.0-1.0 for how sure you are this is a real transaction\n"
    "- CRITICAL ORDER: You MUST call save_transactions FIRST, then mark_emails_processed AFTER.\n"
    "  NEVER call mark_emails_processed before save_transactions. Save first, mark second.\n"
    "- Call save_transactions with ALL transactions in one call, not one by one.\n"
    "- Process every email in the batch\n"
    "</rules>"
)

EXTRACTION_VERIFIER_PROMPT = (
    "Today's date: {today}. Review these extracted transactions. Flag ONLY real issues:\n\n"
    "CHECK:\n"
    "- Amount negative or unreasonably large for the context? → correct to null\n"
    "- Items unit_prices don't add up to total amount? → flag\n"
    "- Type doesn't match description (e.g. type='order' but description says 'cancellation')? → correct type\n"
    "- Missing amount but description contains a clear amount? → extract it\n\n"
    "DO NOT TOUCH:\n"
    "- Dates: NEVER remove or change a date. The worker extracted it from the email.\n"
    "- Payment methods: NEVER remove these.\n"
    "- Items: NEVER remove items the worker extracted.\n\n"
    "Be CONSERVATIVE. Only correct if you are 100% certain there is an error. "
    "Do NOT remove data that looks correct.\n\n"
    "Transactions: {transactions}\n\n"
    "Return corrections: "
    "[{{\"id\": <transaction_id>, \"field\": \"<field_name>\", \"correct_value\": <value>, \"reason\": \"...\"}}] "
    "or [] if all correct.\n"
    "No other text."
)

# --- Pass 3: Correlation ---

CORRELATION_PROMPT_TEMPLATE = (
    "Here are {count} transactions from vendor \"{vendor}\". Your job: identify which ones "
    "represent the SAME purchase and should be merged into one.\n\n"
    "MERGE RULES:\n"
    "- Same order number -> MERGE (order + shipping + delivery = one purchase)\n"
    "- Same amount + same date + same vendor -> MERGE (receipt and payment notification = same charge)\n"
    "- Shipping email (no amount) + order email (has amount) from same vendor within 3 days -> MERGE\n"
    "- A 'subscription' with no amount on the same date as a 'payment' with an amount -> MERGE\n"
    "- A 'cancellation' with no amount is NOT a transaction -- mark for deletion (delete_id, keep_id=null)\n\n"
    "SHIPPING/DELIVERY CARRIERS:\n"
    "- Shipping carriers are NOT the vendor. The real vendor is whoever sold the item.\n"
    "- If a carrier shipping email has the same order/tracking number as another vendor's order → MERGE into the vendor's transaction\n\n"
    "DO NOT MERGE:\n"
    "- Different order numbers = different purchases, PERIOD\n"
    "- Different amounts on different dates = different charges\n"
    "- Two payments of different amounts = distinct, even from the same vendor\n\n"
    "Return a JSON array:\n"
    '[{{"keep_id": <id_to_keep>, "delete_id": <id_to_remove>, "reason": "explanation"}}]\n'
    "To delete a non-transaction (e.g. cancellation notification with no amount):\n"
    '[{{"keep_id": null, "delete_id": <id_to_delete>, "reason": "not a real transaction"}}]\n'
    "If all are distinct real transactions, return: []\n\n"
    "Transactions:\n{transactions_json}"
)

CORRELATION_VERIFIER_PROMPT = (
    "Review these merge instructions for vendor '{vendor}'.\n"
    "RULES: Different order_numbers = NEVER merge. "
    "Same amount + same date + same vendor = likely same.\n\n"
    "Merge instructions: {instructions}\n"
    "Original transactions: {transactions}\n\n"
    "Return: 'approved' if all correct, or "
    "[{{\"keep_id\": <id>, \"delete_id\": <id>, \"action\": \"reject\", \"reason\": \"...\"}}] "
    "for incorrect merges.\n"
    "No other text."
)


# ============================================================
# TOOL DEFINITIONS (Pass 2 — Extraction)
# ============================================================

EXTRACTION_TOOLS = [
    {
        "name": "think",
        "description": (
            "Use this to reason about an email before extracting data. Think about: "
            "what type of transaction is this? Do I need the full body? Have I extracted "
            "all available fields? Is this a duplicate of an existing transaction?"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "thought": {"type": "string", "description": "Your reasoning"},
            },
            "required": ["thought"],
        },
    },
    {
        "name": "get_email_body",
        "description": (
            "Fetch the full text content of an email from the provider API (Gmail or Microsoft). "
            "This makes a live API call — only use when the snippet doesn't contain enough data "
            "(missing amount, invoice number, or line items). Returns plain text, max ~4000 chars. "
            "Always fetch body for orders, receipts, and invoices to get complete item lists and tax details."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_id": {
                    "type": "integer",
                    "description": "The database ID of the email to fetch the body for.",
                },
            },
            "required": ["email_id"],
        },
    },
    {
        "name": "save_transactions",
        "description": (
            "Save one or more extracted financial transactions. Call once per batch with all transactions. "
            "Valid types: invoice, receipt, order, payment, shipping, refund, cancellation, subscription, other. "
            "Set status='complete' when you have vendor + amount + date. "
            "Set status='partial' when any key field is missing. "
            "Confidence: 0.9+ only when all fields clearly extracted from email. "
            "For failed payments, use type='payment' and include 'FAILED' in description."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "transactions": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "email_id": {
                                "type": "integer",
                                "description": "Database ID of the source email.",
                            },
                            "type": {
                                "type": "string",
                                "enum": [
                                    "invoice", "receipt", "order", "payment",
                                    "shipping", "refund", "cancellation",
                                    "subscription", "other",
                                ],
                            },
                            "vendor_name": {"type": "string"},
                            "amount": {
                                "type": "number",
                                "description": "Transaction amount (total including tax). Null if unknown.",
                            },
                            "currency": {
                                "type": "string",
                                "description": "ISO 4217 currency code (EUR, USD, GBP...). Extract from email content.",
                            },
                            "transaction_date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format. Null if unknown.",
                            },
                            "invoice_number": {"type": "string"},
                            "order_number": {"type": "string"},
                            "description": {
                                "type": "string",
                                "description": "Brief description of what the transaction is about.",
                            },
                            "confidence": {
                                "type": "number",
                                "description": "Your confidence 0.0-1.0 that this is a real transaction.",
                            },
                            "status": {
                                "type": "string",
                                "enum": ["partial", "complete"],
                                "description": "complete if vendor+amount+date are known, partial otherwise.",
                            },
                            "amount_tax_excl": {
                                "type": "number",
                                "description": "Amount excluding tax. Null if unknown.",
                            },
                            "tax_amount": {
                                "type": "number",
                                "description": "Tax amount. Null if unknown.",
                            },
                            "tax_rate": {
                                "type": "number",
                                "description": "Tax rate as percentage, e.g. 20.0 for 20%. Null if unknown.",
                            },
                            "payment_method": {
                                "type": "string",
                                "description": "Payment method: debit card, Mastercard, Visa, PayPal, bank transfer, Apple Pay, etc.",
                            },
                            "payment_reference": {
                                "type": "string",
                                "description": "Payment/transaction reference ID from the payment processor.",
                            },
                            "items": {
                                "type": "array",
                                "description": "Line items if available.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "quantity": {"type": "integer"},
                                        "unit_price": {"type": "number"},
                                    },
                                    "required": ["name"],
                                                                    },
                            },
                        },
                        "required": ["email_id", "type", "vendor_name", "confidence", "status"],
                                            },
                },
            },
            "required": ["transactions"],
        },
    },
    {
        "name": "mark_emails_processed",
        "description": (
            "Mark emails as processed (transaction extracted) or ignored (not transactional). "
            "Call this after you've analyzed each email."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "email_ids": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "List of email database IDs to mark.",
                },
                "status": {
                    "type": "string",
                    "enum": ["processed", "ignored"],
                    "description": "Status to set.",
                },
            },
            "required": ["email_ids", "status"],
                    },
            },
]

def _execute_think(user, params):
    """Handle the think tool — just log the thought and return ok."""
    logger.info(f'[Think] {params.get("thought", "")[:300]}')
    return {"ok": True}


def _safe_mark_emails_processed(user, params):
    """Wrapper: only mark as 'processed' if a transaction exists for the email.
    Emails without transactions stay as 'triage_passed' for retry."""
    email_ids = params.get('email_ids', [])
    new_status = params.get('status', 'processed')

    if new_status == 'processed':
        marked_processed = 0
        marked_retry = 0
        for eid in email_ids:
            has_tx = Transaction.objects.filter(user=user, email_id=eid).exists()
            if has_tx:
                Email.objects.filter(id=eid, user=user).update(status='processed')
                marked_processed += 1
            else:
                # Don't mark as processed — keep for retry
                Email.objects.filter(id=eid, user=user).update(status='triage_passed')
                marked_retry += 1
                logger.warning(f'[Safety] Email {eid} has no transaction — kept as triage_passed for retry')
        return {"marked": marked_processed, "retry": marked_retry, "status": new_status}
    else:
        # For 'ignored' status, just pass through
        return _execute_mark_emails_processed(user, params)


EXTRACTION_TOOL_HANDLERS = {
    'think': _execute_think,
    'get_email_body': _execute_get_email_body,
    'save_transactions': _execute_save_transactions,
    'mark_emails_processed': _safe_mark_emails_processed,
}


# ============================================================
# HELPERS
# ============================================================

def _get_api_key():
    """Get the Anthropic API key from settings or environment."""
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        api_key = os.getenv('ANTHROPIC_API_KEY')
    return api_key


def _extract_json(text):
    """
    Extract a JSON array from text that may contain extra content before/after.
    Tries to find the outermost [...] in the text.
    Returns the parsed list, or None if not found.
    """
    if not text:
        return None

    # Strategy 1: Try parsing the full text as JSON directly
    stripped = text.strip()
    if stripped.startswith('['):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            pass

    # Strategy 2: Find the first [ and last ] and try to parse that slice
    first_bracket = text.find('[')
    last_bracket = text.rfind(']')
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidate = text[first_bracket:last_bracket + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 3: Try to find JSON inside a markdown code block
    code_block_match = re.search(r'```(?:json)?\s*(\[[\s\S]*?\])\s*```', text)
    if code_block_match:
        try:
            return json.loads(code_block_match.group(1))
        except json.JSONDecodeError:
            pass

    return None


def _call_api_with_retry(client, **kwargs):
    """Call Anthropic API with retry on rate limit / overload errors."""
    for attempt in range(MAX_RETRIES):
        try:
            return client.messages.create(**kwargs)
        except anthropic.RateLimitError:
            if attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f'Rate limited, retrying in {delay}s (attempt {attempt + 1})')
                time.sleep(delay)
            else:
                raise
        except anthropic.APIError as e:
            if e.status_code in (529,) and attempt < MAX_RETRIES - 1:
                delay = RETRY_BASE_DELAY * (2 ** attempt)
                logger.warning(f'API overloaded, retrying in {delay}s')
                time.sleep(delay)
            else:
                raise


def _get_response_text(response):
    """Extract text content from an Anthropic API response."""
    text = ""
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            text += block.text
    return text


def _verify(client, prompt, rate_limiter, model=None):
    """
    Run a verifier LLM call. Returns parsed JSON corrections or empty list.
    Verifier has fresh context — only sees the output to verify.
    """
    if rate_limiter:
        rate_limiter.wait_if_needed()

    verify_model = model or MODEL_TRIAGE

    try:
        response = _call_api_with_retry(
            client,
            model=verify_model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        if rate_limiter and hasattr(response, 'usage') and response.usage:
            rate_limiter.record_usage(response.usage.input_tokens)

        response_text = _get_response_text(response)

        # Check for "approved" (used by correlation verifier)
        if response_text.strip().lower() == 'approved':
            return 'approved'

        corrections = _extract_json(response_text)
        if corrections is None:
            return []
        return corrections

    except Exception as e:
        logger.error(f'Verifier error: {e}')
        return []


# ============================================================
# PASS 1 — TRIAGE (Worker + Verifier)
# ============================================================

def _triage_single_batch(client, emails_data, rate_limiter):
    """
    Worker: Run triage on a single batch of emails.
    Returns list of dicts: [{id, transactional: bool}].
    """
    email_lines = []
    for e in emails_data:
        email_lines.append(
            f'- id={e["id"]}, from="{e["from_address"]}", subject="{e["subject"]}", '
            f'snippet="{e["snippet"][:120]}", date="{e["date"]}"'
        )
    emails_text = "\n".join(email_lines)

    user_msg = f"{TRIAGE_WORKER_PROMPT}\nEmails ({len(emails_data)}):\n{emails_text}"

    if rate_limiter:
        rate_limiter.wait_if_needed()

    response = _call_api_with_retry(
        client,
        model=MODEL_TRIAGE,
        max_tokens=2048,
        messages=[{"role": "user", "content": user_msg}],
    )

    if rate_limiter and hasattr(response, 'usage') and response.usage:
        rate_limiter.record_usage(response.usage.input_tokens)

    response_text = _get_response_text(response)
    results = _extract_json(response_text)

    if results is None:
        logger.error(f'[Triage] Failed to parse JSON response: {response_text[:500]}')
        # Fail safe: treat all as transactional so they proceed to extraction
        return [{"id": e["id"], "transactional": True} for e in emails_data]

    # Ensure all emails in the batch are accounted for
    valid_ids = {e["id"] for e in emails_data}
    mentioned_ids = {item.get("id") for item in results}

    for e in emails_data:
        if e["id"] not in mentioned_ids:
            logger.warning(f'[Triage] Email {e["id"]} not in LLM response, treating as transactional')
            results.append({"id": e["id"], "transactional": True})

    # Filter out unknown IDs
    results = [r for r in results if r.get("id") in valid_ids]

    return results


def _process_triage_batch(api_key, emails_data, batch_num, total_batches, rate_limiter):
    """Process a single triage batch in its own thread. Returns list of triage decisions."""
    thread_id = threading.current_thread().name
    logger.info(
        f'[Triage] Batch {batch_num}/{total_batches} -- {len(emails_data)} emails (thread-{thread_id})'
    )

    client = anthropic.Anthropic(api_key=api_key)

    try:
        decisions = _triage_single_batch(client, emails_data, rate_limiter)
        transactional = sum(1 for d in decisions if d.get("transactional"))
        ignored = len(decisions) - transactional
        logger.info(
            f'[Triage] Batch {batch_num}/{total_batches} done -- '
            f'{transactional} transactional, {ignored} ignored (thread-{thread_id})'
        )
        return decisions
    except Exception as e:
        logger.error(f'[Triage] Batch {batch_num} error (thread-{thread_id}): {e}')
        # Fail safe: treat all as transactional
        return [{"id": em["id"], "transactional": True} for em in emails_data]


def _run_triage_verifier(client, all_decisions, emails_data, rate_limiter):
    """
    Verifier: independent LLM call reviewing worker's triage decisions.
    Returns list of corrections: [{id, should_be, reason}].
    """
    if not all_decisions:
        return []

    # Build compact decisions with enough context for the verifier
    emails_by_id = {e["id"]: e for e in emails_data}
    decisions_with_context = []
    for d in all_decisions:
        email = emails_by_id.get(d["id"], {})
        decisions_with_context.append({
            "id": d["id"],
            "transactional": d.get("transactional", False),
            "subject": email.get("subject", ""),
            "from": email.get("from_address", ""),
            "snippet": email.get("snippet", "")[:80],
        })

    prompt = TRIAGE_VERIFIER_PROMPT.format(
        decisions=json.dumps(decisions_with_context, ensure_ascii=False)
    )

    logger.info(f'[Triage-Verify] Reviewing {len(all_decisions)} triage decisions')
    corrections = _verify(client, prompt, rate_limiter)

    if isinstance(corrections, list) and corrections:
        logger.info(f'[Triage-Verify] Found {len(corrections)} corrections')
    else:
        logger.info('[Triage-Verify] All decisions approved')
        corrections = []

    return corrections


def _apply_triage_corrections(all_decisions, corrections):
    """Apply verifier corrections to triage decisions in place."""
    if not corrections:
        return

    corrections_map = {c["id"]: c["should_be"] for c in corrections if "id" in c and "should_be" in c}

    for decision in all_decisions:
        if decision["id"] in corrections_map:
            old_val = decision.get("transactional")
            new_val = corrections_map[decision["id"]]
            if old_val != new_val:
                reason = next(
                    (c.get("reason", "") for c in corrections if c.get("id") == decision["id"]),
                    ""
                )
                logger.info(
                    f'[Triage-Verify] Corrected email {decision["id"]}: '
                    f'{old_val} -> {new_val} ({reason})'
                )
                decision["transactional"] = new_val


def _run_triage_pass(user, api_key, rate_limiter):
    """
    Pass 1: Triage -- classify emails as transactional or not.
    Worker classifies in batches, Verifier reviews decisions.
    Returns stats dict.
    """
    logger.info('[Triage] === PASS 1 START ===')

    new_emails = list(
        Email.objects.filter(user=user, status=Email.Status.NEW)
        .order_by('-date')
        .values('id', 'from_address', 'from_name', 'subject', 'snippet', 'date')
    )

    if not new_emails:
        logger.info('[Triage] No new emails to triage')
        return {'triage_transactional': 0, 'triage_ignored': 0, 'triage_total': 0}

    # Prepare email data for the LLM
    emails_data = []
    for e in new_emails:
        emails_data.append({
            'id': e['id'],
            'from_address': e['from_address'],
            'subject': e['subject'],
            'snippet': e['snippet'],
            'date': e['date'].isoformat() if e['date'] else '',
        })

    # Split into batches
    all_batches = [
        emails_data[i:i + TRIAGE_BATCH_SIZE]
        for i in range(0, len(emails_data), TRIAGE_BATCH_SIZE)
    ]
    total_batches = len(all_batches)
    logger.info(
        f'[Triage] {len(emails_data)} emails in {total_batches} batches '
        f'(max {TRIAGE_MAX_CONCURRENT} concurrent)'
    )

    # --- Worker: parallel triage batches ---
    all_decisions = []

    with ThreadPoolExecutor(max_workers=TRIAGE_MAX_CONCURRENT) as executor:
        futures = {}
        for batch_idx, batch_data in enumerate(all_batches):
            batch_num = batch_idx + 1
            if batch_idx > 0:
                time.sleep(0.5)
            future = executor.submit(
                _process_triage_batch,
                api_key, batch_data, batch_num, total_batches, rate_limiter,
            )
            futures[future] = batch_num

        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                decisions = future.result()
                all_decisions.extend(decisions)
            except Exception as e:
                logger.error(f'[Triage] Batch {batch_num} raised unexpected exception: {e}')

    # --- Verifier: review all decisions ---
    client = anthropic.Anthropic(api_key=api_key)
    corrections = _run_triage_verifier(client, all_decisions, emails_data, rate_limiter)
    _apply_triage_corrections(all_decisions, corrections)

    # Update statuses in DB
    transactional_ids = [d["id"] for d in all_decisions if d.get("transactional")]
    ignored_ids = [d["id"] for d in all_decisions if not d.get("transactional")]

    if ignored_ids:
        Email.objects.filter(user=user, id__in=ignored_ids).update(
            status=Email.Status.IGNORED
        )
    if transactional_ids:
        Email.objects.filter(user=user, id__in=transactional_ids).update(
            status=Email.Status.TRIAGE_PASSED
        )

    logger.info(
        f'[Triage] === PASS 1 DONE === '
        f'{len(transactional_ids)} transactional, {len(ignored_ids)} ignored '
        f'out of {len(emails_data)}'
    )

    return {
        'triage_transactional': len(transactional_ids),
        'triage_ignored': len(ignored_ids),
        'triage_total': len(emails_data),
    }


# ============================================================
# PASS 2 — EXTRACTION (Worker + Verifier)
# ============================================================

def _extraction_single_batch(client, user, emails_data, batch_stats, rate_limiter):
    """
    Worker: Run extraction on a single batch of triage-passed emails using tool_use.
    Modifies batch_stats in place.
    """
    emails_text = json.dumps(emails_data, default=str, ensure_ascii=False)

    user_msg = (
        f"Extract transaction data from these {len(emails_data)} transactional emails.\n"
        f"For each email, extract: vendor_name, amount, currency, transaction_date, type, "
        f"invoice_number, order_number, description. "
        f"Also extract if present: amount_tax_excl, tax_amount, tax_rate, payment_method, "
        f"payment_reference, items.\n"
        f"If the snippet is empty or missing amounts, use get_email_body to fetch the full content.\n"
        f"Save each transaction with save_transactions.\n"
        f"Mark all emails as processed when done.\n\n"
        f"Emails:\n{emails_text}"
    )

    messages = [{"role": "user", "content": user_msg}]

    if rate_limiter:
        rate_limiter.wait_if_needed()

    response = _call_api_with_retry(
        client,
        model=MODEL_EXTRACTION,
        max_tokens=8192,
        system=EXTRACTION_SYSTEM_PROMPT,
        tools=EXTRACTION_TOOLS,
        messages=messages,
    )
    batch_stats["api_calls"] += 1

    if rate_limiter and hasattr(response, 'usage') and response.usage:
        rate_limiter.record_usage(response.usage.input_tokens)

    # Agentic tool-use loop
    max_iterations = 15
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(f'  [Extraction] Iteration {iteration} | stop_reason={response.stop_reason}')

        for block in response.content:
            if hasattr(block, 'text') and block.text:
                logger.info(f'  [Extraction] Agent: {block.text[:300]}')

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        assistant_content = response.content

        for block in assistant_content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                logger.info(
                    f'  [Extraction] TOOL: {tool_name}({json.dumps(tool_input, default=str)[:300]})'
                )

                handler = EXTRACTION_TOOL_HANDLERS.get(tool_name)
                is_error = False
                if handler:
                    try:
                        result = handler(user, tool_input)
                        logger.info(
                            f'  [Extraction] RESULT: {tool_name} -> '
                            f'{json.dumps(result, default=str)[:300]}'
                        )

                        if tool_name == 'save_transactions':
                            batch_stats["transactions_created"] += result.get("created", 0)
                            batch_stats["transactions_updated"] += result.get("updated", 0)
                        elif tool_name == 'mark_emails_processed':
                            if tool_input.get('status') == 'processed':
                                batch_stats["emails_processed"] += result.get("marked", 0)
                            elif tool_input.get('status') == 'ignored':
                                batch_stats["emails_ignored"] += result.get("marked", 0)

                    except Exception as e:
                        logger.error(f'  [Extraction] TOOL ERROR: {tool_name}: {e}')
                        result = {"error": str(e)}
                        is_error = True
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}
                    is_error = True

                tool_result_entry = {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                }
                if is_error:
                    tool_result_entry["is_error"] = True
                tool_results.append(tool_result_entry)

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

        if rate_limiter:
            rate_limiter.wait_if_needed()

        response = _call_api_with_retry(
            client,
            model=MODEL_EXTRACTION,
            max_tokens=8192,
            system=EXTRACTION_SYSTEM_PROMPT,
            tools=EXTRACTION_TOOLS,
            messages=messages,
        )
        batch_stats["api_calls"] += 1

        if rate_limiter and hasattr(response, 'usage') and response.usage:
            rate_limiter.record_usage(response.usage.input_tokens)


def _process_extraction_batch(api_key, user, emails_data, batch_num, total_batches, rate_limiter):
    """Process a single extraction batch in its own thread. Returns batch_stats dict."""
    thread_id = threading.current_thread().name
    logger.info(
        f'[Extraction] Batch {batch_num}/{total_batches} -- '
        f'{len(emails_data)} emails (thread-{thread_id})'
    )

    client = anthropic.Anthropic(api_key=api_key)

    batch_stats = {
        "transactions_created": 0,
        "transactions_updated": 0,
        "emails_processed": 0,
        "emails_ignored": 0,
        "api_calls": 0,
        "errors": 0,
    }

    try:
        _extraction_single_batch(client, user, emails_data, batch_stats, rate_limiter)
    except anthropic.RateLimitError:
        logger.warning(
            f'[Extraction] Rate limited on batch {batch_num} (thread-{thread_id}), waiting 60s...'
        )
        time.sleep(60)
        try:
            _extraction_single_batch(client, user, emails_data, batch_stats, rate_limiter)
        except Exception as e:
            logger.error(
                f'[Extraction] Batch {batch_num} failed after retry (thread-{thread_id}): {e}'
            )
            batch_stats["errors"] += 1
    except Exception as e:
        logger.error(f'[Extraction] Batch {batch_num} error (thread-{thread_id}): {e}')
        batch_stats["errors"] += 1

    logger.info(
        f'[Extraction] Batch {batch_num}/{total_batches} done -- '
        f'created={batch_stats["transactions_created"]}, '
        f'updated={batch_stats["transactions_updated"]}, '
        f'processed={batch_stats["emails_processed"]} (thread-{thread_id})'
    )
    return batch_stats


def _run_extraction_verifier(user, client, rate_limiter):
    """
    Verifier: independent LLM call reviewing recently extracted transactions.
    Returns list of corrections.
    """
    recent_transactions = list(
        Transaction.objects.filter(user=user).order_by('-processed_at')[:100]
    )

    if not recent_transactions:
        return []

    tx_data = []
    for tx in recent_transactions:
        tx_data.append({
            'id': tx.id,
            'type': tx.type,
            'vendor_name': tx.vendor_name,
            'amount': str(tx.amount) if tx.amount else None,
            'currency': tx.currency,
            'transaction_date': tx.transaction_date.isoformat() if tx.transaction_date else None,
            'description': tx.description,
            'items': tx.items,
            'amount_tax_excl': str(tx.amount_tax_excl) if tx.amount_tax_excl else None,
            'tax_amount': str(tx.tax_amount) if tx.tax_amount else None,
            'tax_rate': str(tx.tax_rate) if tx.tax_rate else None,
            'status': tx.status,
            'confidence': tx.confidence,
        })

    from django.utils import timezone as dj_tz
    prompt = EXTRACTION_VERIFIER_PROMPT.format(
        today=dj_tz.now().strftime('%Y-%m-%d'),
        transactions=json.dumps(tx_data, ensure_ascii=False)
    )

    logger.info(f'[Extraction-Verify] Reviewing {len(tx_data)} extracted transactions')
    corrections = _verify(client, prompt, rate_limiter, model=MODEL_EXTRACTION)

    if isinstance(corrections, list) and corrections:
        logger.info(f'[Extraction-Verify] Found {len(corrections)} corrections')
    else:
        logger.info('[Extraction-Verify] All extractions approved')
        corrections = []

    return corrections


def _apply_extraction_corrections(user, corrections):
    """Apply verifier corrections to extracted transactions."""
    if not corrections:
        return

    for correction in corrections:
        tx_id = correction.get('id')
        field = correction.get('field')
        correct_value = correction.get('correct_value')
        reason = correction.get('reason', '')

        if not tx_id or not field:
            continue

        try:
            tx = Transaction.objects.get(id=tx_id, user=user)
        except Transaction.DoesNotExist:
            logger.warning(f'[Extraction-Verify] Transaction {tx_id} not found')
            continue

        # Only allow updating known fields
        allowed_fields = {
            'type', 'vendor_name', 'amount', 'currency', 'transaction_date',
            'invoice_number', 'order_number', 'description', 'confidence',
            'status', 'amount_tax_excl', 'tax_amount', 'tax_rate',
            'payment_method', 'payment_reference',
        }

        if field not in allowed_fields:
            logger.warning(f'[Extraction-Verify] Field "{field}" not allowed for correction')
            continue

        old_value = getattr(tx, field, None)
        logger.info(
            f'[Extraction-Verify] Correcting tx {tx_id} field "{field}": '
            f'{old_value} -> {correct_value} ({reason})'
        )

        if field in ('amount', 'amount_tax_excl', 'tax_amount', 'tax_rate'):
            if correct_value is not None:
                try:
                    correct_value = Decimal(str(correct_value))
                except Exception:
                    logger.warning(f'[Extraction-Verify] Cannot convert "{correct_value}" to Decimal')
                    continue

        setattr(tx, field, correct_value)
        tx.save()


def _run_extraction_pass(user, api_key, rate_limiter):
    """
    Pass 2: Extraction -- extract structured transaction data from triage-passed emails.
    Worker extracts with tool_use, Verifier reviews results.
    Returns stats dict.
    """
    logger.info('[Extraction] === PASS 2 START ===')

    triage_passed_emails = list(
        Email.objects.filter(user=user, status=Email.Status.TRIAGE_PASSED)
        .order_by('-date')
        .values('id', 'from_address', 'from_name', 'subject', 'snippet', 'date',
                'has_attachments', 'provider')
    )

    if not triage_passed_emails:
        logger.info('[Extraction] No triage-passed emails to extract')
        return {
            'extraction_transactions_created': 0,
            'extraction_transactions_updated': 0,
            'extraction_emails_processed': 0,
            'extraction_emails_ignored': 0,
            'extraction_api_calls': 0,
            'extraction_errors': 0,
        }

    # Prepare email data
    emails_data_all = []
    for e in triage_passed_emails:
        emails_data_all.append({
            'id': e['id'],
            'from_address': e['from_address'],
            'from_name': e['from_name'],
            'subject': e['subject'],
            'snippet': e['snippet'],
            'date': e['date'].isoformat() if e['date'] else '',
            'has_attachments': e['has_attachments'],
        })

    # Split into batches
    all_batches = [
        emails_data_all[i:i + EXTRACTION_BATCH_SIZE]
        for i in range(0, len(emails_data_all), EXTRACTION_BATCH_SIZE)
    ]
    total_batches = len(all_batches)
    logger.info(
        f'[Extraction] {len(emails_data_all)} emails in {total_batches} batches '
        f'(max {EXTRACTION_MAX_CONCURRENT} concurrent)'
    )

    stats = {
        'extraction_transactions_created': 0,
        'extraction_transactions_updated': 0,
        'extraction_emails_processed': 0,
        'extraction_emails_ignored': 0,
        'extraction_api_calls': 0,
        'extraction_errors': 0,
    }
    stats_lock = threading.Lock()

    # --- Worker: parallel extraction batches ---
    with ThreadPoolExecutor(max_workers=EXTRACTION_MAX_CONCURRENT) as executor:
        futures = {}
        for batch_idx, batch_data in enumerate(all_batches):
            batch_num = batch_idx + 1
            if batch_idx > 0:
                time.sleep(1)
            future = executor.submit(
                _process_extraction_batch,
                api_key, user, batch_data, batch_num, total_batches, rate_limiter,
            )
            futures[future] = batch_num

        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                batch_stats = future.result()
                with stats_lock:
                    stats['extraction_transactions_created'] += batch_stats.get('transactions_created', 0)
                    stats['extraction_transactions_updated'] += batch_stats.get('transactions_updated', 0)
                    stats['extraction_emails_processed'] += batch_stats.get('emails_processed', 0)
                    stats['extraction_emails_ignored'] += batch_stats.get('emails_ignored', 0)
                    stats['extraction_api_calls'] += batch_stats.get('api_calls', 0)
                    stats['extraction_errors'] += batch_stats.get('errors', 0)
            except Exception as e:
                logger.error(f'[Extraction] Batch {batch_num} raised unexpected exception: {e}')
                with stats_lock:
                    stats['extraction_errors'] += 1

    # --- Verifier: review extracted transactions ---
    client = anthropic.Anthropic(api_key=api_key)
    extraction_corrections = _run_extraction_verifier(user, client, rate_limiter)
    _apply_extraction_corrections(user, extraction_corrections)

    logger.info(
        f'[Extraction] === PASS 2 DONE === '
        f'created={stats["extraction_transactions_created"]}, '
        f'updated={stats["extraction_transactions_updated"]}, '
        f'processed={stats["extraction_emails_processed"]}, '
        f'ignored={stats["extraction_emails_ignored"]}, '
        f'api_calls={stats["extraction_api_calls"]}'
    )

    return stats


# ============================================================
# PASS 3 — CORRELATION (Worker + Verifier)
# ============================================================

def _run_correlation_pass(user, api_key, rate_limiter):
    """
    Pass 3: Correlation -- find and merge duplicate/related transactions per vendor.
    Worker suggests merges, Verifier checks each per-vendor group.
    Returns stats dict.
    """
    logger.info('[Correlation] === PASS 3 START ===')

    all_transactions = list(Transaction.objects.filter(user=user).order_by('id'))

    if not all_transactions:
        logger.info('[Correlation] No transactions to correlate')
        return {'correlation_merges': 0, 'correlation_vendors_checked': 0}

    # Group by normalized vendor name
    vendor_groups = defaultdict(list)
    for tx in all_transactions:
        normalized = _normalize_vendor_name(tx.vendor_name)
        if normalized:
            vendor_groups[normalized].append(tx)

    # Filter to only groups with 2+ transactions
    multi_groups = {vendor: txs for vendor, txs in vendor_groups.items() if len(txs) >= 2}

    if not multi_groups:
        logger.info('[Correlation] No vendor groups with 2+ transactions')
        return {'correlation_merges': 0, 'correlation_vendors_checked': 0}

    logger.info(f'[Correlation] {len(multi_groups)} vendor groups with 2+ transactions')

    client = anthropic.Anthropic(api_key=api_key)

    total_merges = 0
    vendors_checked = 0

    for vendor_name, txs in multi_groups.items():
        vendors_checked += 1

        # Build transaction data for the LLM (include email_subject)
        tx_data = []
        for tx in txs:
            entry = {
                'id': tx.id,
                'type': tx.type,
                'vendor_name': tx.vendor_name,
                'amount': str(tx.amount) if tx.amount else None,
                'currency': tx.currency,
                'transaction_date': tx.transaction_date.isoformat() if tx.transaction_date else None,
                'invoice_number': tx.invoice_number,
                'order_number': tx.order_number,
                'description': tx.description,
                'status': tx.status,
            }
            # Add email subject for extra context
            if tx.email:
                entry['email_subject'] = tx.email.subject
            tx_data.append(entry)

        transactions_json = json.dumps(tx_data, ensure_ascii=False, indent=2)

        # --- Worker: suggest merges ---
        prompt = CORRELATION_PROMPT_TEMPLATE.format(
            count=len(txs),
            vendor=vendor_name,
            transactions_json=transactions_json,
        )

        if rate_limiter:
            rate_limiter.wait_if_needed()

        try:
            response = _call_api_with_retry(
                client,
                model=MODEL_CORRELATION,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            if rate_limiter and hasattr(response, 'usage') and response.usage:
                rate_limiter.record_usage(response.usage.input_tokens)

        except Exception as e:
            logger.error(f'[Correlation] API error for vendor "{vendor_name}": {e}')
            continue

        response_text = _get_response_text(response)
        merge_instructions = _extract_json(response_text)

        if merge_instructions is None:
            logger.warning(
                f'[Correlation] Could not parse JSON for vendor "{vendor_name}": '
                f'{response_text[:300]}'
            )
            continue

        if not merge_instructions:
            logger.info(
                f'[Correlation] Vendor "{vendor_name}": all {len(txs)} transactions are distinct'
            )
            continue

        # --- Verifier: check merge instructions ---
        verifier_prompt = CORRELATION_VERIFIER_PROMPT.format(
            vendor=vendor_name,
            instructions=json.dumps(merge_instructions, ensure_ascii=False),
            transactions=transactions_json,
        )

        logger.info(
            f'[Correlation-Verify] Reviewing {len(merge_instructions)} merge instructions '
            f'for vendor "{vendor_name}"'
        )
        verifier_result = _verify(client, verifier_prompt, rate_limiter, model=MODEL_CORRELATION)

        # Apply verifier rejections
        rejected_pairs = set()
        if isinstance(verifier_result, list) and verifier_result:
            for rejection in verifier_result:
                if rejection.get('action') == 'reject':
                    pair = (rejection.get('keep_id'), rejection.get('delete_id'))
                    rejected_pairs.add(pair)
                    logger.info(
                        f'[Correlation-Verify] Rejected merge: keep={pair[0]}, '
                        f'delete={pair[1]}, reason={rejection.get("reason", "")}'
                    )
        elif verifier_result == 'approved':
            logger.info(f'[Correlation-Verify] All merges approved for vendor "{vendor_name}"')

        # Execute approved merge instructions
        tx_by_id = {tx.id: tx for tx in txs}
        deleted_ids = set()

        for instruction in merge_instructions:
            keep_id = instruction.get('keep_id')
            delete_id = instruction.get('delete_id')
            reason = instruction.get('reason', 'LLM correlation')

            if delete_id is None:
                logger.warning(f'[Correlation] Invalid merge instruction (no delete_id): {instruction}')
                continue

            # Skip if verifier rejected this merge
            if (keep_id, delete_id) in rejected_pairs:
                logger.info(
                    f'[Correlation] Skipping rejected merge: keep={keep_id}, delete={delete_id}'
                )
                continue

            if delete_id in deleted_ids:
                logger.info(f'[Correlation] Transaction {delete_id} already deleted, skipping')
                continue

            delete_tx = tx_by_id.get(delete_id)
            if not delete_tx:
                logger.warning(f'[Correlation] Transaction {delete_id} not found')
                continue

            # keep_id=null means "just delete, not a real transaction"
            if keep_id is None:
                logger.info(
                    f'[Correlation] Deleting non-transaction {delete_id} '
                    f'for vendor "{vendor_name}": {reason}'
                )
                delete_tx.delete()
                deleted_ids.add(delete_id)
                total_merges += 1
                continue

            keep_tx = tx_by_id.get(keep_id)
            if not keep_tx:
                logger.warning(f'[Correlation] Keep transaction {keep_id} not found')
                continue

            if keep_id in deleted_ids:
                logger.warning(
                    f'[Correlation] Cannot keep transaction {keep_id} -- already deleted'
                )
                continue

            # Merge: absorb data from delete_tx into keep_tx
            logger.info(
                f'[Correlation] Merging transaction {delete_id} into {keep_id} '
                f'for vendor "{vendor_name}": {reason}'
            )

            if keep_tx.amount is None and delete_tx.amount is not None:
                keep_tx.amount = delete_tx.amount
            if not keep_tx.transaction_date and delete_tx.transaction_date:
                keep_tx.transaction_date = delete_tx.transaction_date
            if not keep_tx.order_number and delete_tx.order_number:
                keep_tx.order_number = delete_tx.order_number
            if not keep_tx.invoice_number and delete_tx.invoice_number:
                keep_tx.invoice_number = delete_tx.invoice_number
            if not keep_tx.description and delete_tx.description:
                keep_tx.description = delete_tx.description
            if keep_tx.amount_tax_excl is None and delete_tx.amount_tax_excl is not None:
                keep_tx.amount_tax_excl = delete_tx.amount_tax_excl
            if keep_tx.tax_amount is None and delete_tx.tax_amount is not None:
                keep_tx.tax_amount = delete_tx.tax_amount
            if keep_tx.tax_rate is None and delete_tx.tax_rate is not None:
                keep_tx.tax_rate = delete_tx.tax_rate
            if not keep_tx.payment_method and delete_tx.payment_method:
                keep_tx.payment_method = delete_tx.payment_method
            if not keep_tx.payment_reference and delete_tx.payment_reference:
                keep_tx.payment_reference = delete_tx.payment_reference
            if not keep_tx.items and delete_tx.items:
                keep_tx.items = delete_tx.items
            keep_tx.confidence = max(keep_tx.confidence, delete_tx.confidence)

            # Upgrade status if now complete
            if keep_tx.vendor_name and keep_tx.amount is not None and keep_tx.transaction_date:
                keep_tx.status = 'complete'

            keep_tx.save()
            delete_tx.delete()
            deleted_ids.add(delete_id)
            total_merges += 1

        logger.info(
            f'[Correlation] Vendor "{vendor_name}": merged {len(deleted_ids)} '
            f'out of {len(txs)} transactions'
        )

    # --- Cross-vendor correlation (shipping carriers → real vendors) ---
    # Send ALL shipping transactions (no amount) + ALL order transactions to the AI
    # The AI decides which shipping belongs to which order — no hardcoded carrier list
    remaining_txs = list(Transaction.objects.filter(user=user).order_by('id'))
    shipping_txs = [t for t in remaining_txs if t.type == 'shipping' and t.amount is None]
    order_txs = [t for t in remaining_txs if t.type in ('order', 'receipt', 'invoice') and t.amount is not None]

    if shipping_txs and order_txs:
        all_for_cross = shipping_txs + order_txs
        cross_data = []
        for tx in all_for_cross:
            cross_data.append({
                'id': tx.id,
                'type': tx.type,
                'vendor_name': tx.vendor_name,
                'amount': str(tx.amount) if tx.amount else None,
                'transaction_date': tx.transaction_date.isoformat() if tx.transaction_date else None,
                'order_number': tx.order_number,
                'description': tx.description[:100] if tx.description else '',
            })

        cross_prompt = (
            "Here are shipping transactions (no amount) and order/receipt transactions (with amount) "
            "from DIFFERENT vendors. Some shipping emails may be delivery notifications for an order "
            "from another vendor (e.g. a shipping company delivering a store's order).\n\n"
            "If a shipping transaction is clearly the delivery of an existing order "
            "(same order number, similar dates, description matches), merge them.\n\n"
            "RULES:\n"
            "- Same order/tracking number = MERGE (delete the shipping, keep the order)\n"
            "- Different order numbers or no clear link = DO NOT MERGE\n"
            "- When in doubt, do NOT merge\n\n"
            "Return JSON array:\n"
            '[{"keep_id": <order_id>, "delete_id": <shipping_id>, "reason": "..."}]\n'
            "or [] if no cross-vendor matches.\n\n"
            f"Transactions:\n{json.dumps(cross_data, ensure_ascii=False, indent=2)}"
        )

        if rate_limiter:
            rate_limiter.wait_if_needed()

        try:
            response = _call_api_with_retry(
                client, model=MODEL_CORRELATION, max_tokens=2048,
                messages=[{"role": "user", "content": cross_prompt}],
            )
            if rate_limiter and hasattr(response, 'usage') and response.usage:
                rate_limiter.record_usage(response.usage.input_tokens)

            response_text = _get_response_text(response)
            cross_instructions = _extract_json(response_text)

            if cross_instructions:
                tx_by_id = {tx.id: tx for tx in all_for_cross}
                for instr in cross_instructions:
                    keep_id = instr.get('keep_id')
                    delete_id = instr.get('delete_id')
                    reason = instr.get('reason', '')
                    if keep_id and delete_id and delete_id in tx_by_id:
                        logger.info(
                            f'[Correlation] Cross-vendor merge: shipping id={delete_id} '
                            f'({tx_by_id[delete_id].vendor_name}) → order id={keep_id} '
                            f'({tx_by_id.get(keep_id, {}).vendor_name if keep_id in tx_by_id else "?"}): {reason}'
                        )
                        tx_by_id[delete_id].delete()
                        total_merges += 1
                else:
                    logger.info('[Correlation] No cross-vendor matches found')
        except Exception as e:
            logger.error(f'[Correlation] Cross-vendor correlation error: {e}')

    logger.info(
        f'[Correlation] === PASS 3 DONE === '
        f'{total_merges} merges across {vendors_checked} vendors'
    )

    return {
        'correlation_merges': total_merges,
        'correlation_vendors_checked': vendors_checked,
    }


# ============================================================
# PASS 4 — COMPUTATION (Pure Python, no LLM)
# ============================================================

def _run_computation_pass(user):
    """
    Pass 4: Pure Python -- compute derivable tax fields. No LLM.
    - If total + tax_amount known -> amount_tax_excl = total - tax_amount
    - If total + tax_rate known -> tax_amount = total * rate / (100 + rate), amount_tax_excl = total - tax_amount
    - If amount_tax_excl + tax_amount known -> total = amount_tax_excl + tax_amount
    - Round to 2 decimals
    """
    logger.info('[Computation] === PASS 4 START ===')

    updated = 0
    for tx in Transaction.objects.filter(user=user):
        changed = False

        # total + tax_amount known -> amount_tax_excl = total - tax_amount
        if tx.amount and tx.tax_amount and not tx.amount_tax_excl:
            tx.amount_tax_excl = (tx.amount - tx.tax_amount).quantize(Decimal('0.01'))
            changed = True

        # total + tax_rate known -> tax_amount and amount_tax_excl
        if tx.amount and tx.tax_rate and not tx.tax_amount:
            rate = tx.tax_rate / Decimal('100')
            tx.tax_amount = (tx.amount * rate / (1 + rate)).quantize(Decimal('0.01'))
            tx.amount_tax_excl = (tx.amount - tx.tax_amount).quantize(Decimal('0.01'))
            changed = True

        # amount_tax_excl + tax_amount known -> total = amount_tax_excl + tax_amount
        if tx.amount_tax_excl and tx.tax_amount and not tx.amount:
            tx.amount = (tx.amount_tax_excl + tx.tax_amount).quantize(Decimal('0.01'))
            changed = True

        if changed:
            tx.save()
            updated += 1

    logger.info(f'[Computation] === PASS 4 DONE === {updated} transactions updated')

    return {"computation_updated": updated}


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_pipeline(user):
    """
    Run the full multi-pass email processing pipeline.

    Pass 1: Triage (Worker + Verifier) -- classify emails as transactional or not
    Pass 2: Extraction (Worker + Verifier) -- extract structured data with tool_use
    Pass 3: Correlation (Worker + Verifier) -- merge related transactions per vendor
    Pass 4: Computation (pure Python) -- compute derivable tax fields

    Returns a combined stats dict.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    logger.info('====== PIPELINE START ======')

    # Shared rate limiter across all passes
    rate_limiter = RateLimiter()

    # Pass 1: Triage
    triage_stats = _run_triage_pass(user, api_key, rate_limiter)

    # Pass 2: Extraction
    extraction_stats = _run_extraction_pass(user, api_key, rate_limiter)

    # Pass 3: Correlation
    correlation_stats = _run_correlation_pass(user, api_key, rate_limiter)

    # Pass 4: Computation (pure Python, no LLM)
    computation_stats = _run_computation_pass(user)

    # Combine all stats
    stats = {
        **triage_stats,
        **extraction_stats,
        **correlation_stats,
        **computation_stats,
    }

    logger.info(f'====== PIPELINE DONE ====== Stats: {json.dumps(stats)}')

    return stats
