"""
Multi-pass email classification pipeline.

Architecture:
  1. Prefilter (rule-based, already exists)
  2. Pass 1 -- TRIAGE: "Is this email transactional? yes/no" (fast, big batches of 40)
  3. Pass 2 -- EXTRACTION: "Extract structured data from this transactional email" (smaller batches of 15, may fetch body)
  4. Pass 3 -- CORRELATION: "These transactions from the same vendor -- should they be merged?" (per-vendor groups)
  5. Return final stats
"""

import json
import logging
import os
import re
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

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
from emails.services.prefilter import prefilter_emails
from emails.services.token_refresh import get_valid_token

logger = logging.getLogger(__name__)

# --- Constants ---

TRIAGE_BATCH_SIZE = 40
TRIAGE_MAX_CONCURRENT = 3

EXTRACTION_BATCH_SIZE = 15
EXTRACTION_MAX_CONCURRENT = 2

MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds

MODEL = "claude-haiku-4-5-20251001"

# --- Tool definitions for extraction pass (subset of agent.py tools) ---

EXTRACTION_TOOLS = [
    {
        "name": "get_email_body",
        "description": (
            "Fetch the full body (text content) of a specific email from the provider API. "
            "Use this when the snippet alone doesn't contain enough info (e.g., missing amount, invoice number). "
            "Returns the plain text body of the email."
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
            "Save one or more extracted transactions to the database. "
            "Use structured data with all fields you could extract. "
            "Set status to 'complete' if you have vendor + amount + date, otherwise 'partial'."
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
                                "enum": ["invoice", "receipt", "order", "payment",
                                         "shipping", "refund", "cancellation", "subscription", "other"],
                            },
                            "vendor_name": {"type": "string"},
                            "amount": {
                                "type": "number",
                                "description": "Transaction amount. Null if unknown.",
                            },
                            "currency": {
                                "type": "string",
                                "description": "ISO 4217 currency code (EUR, USD, GBP...). Default: EUR.",
                            },
                            "transaction_date": {
                                "type": "string",
                                "description": "Date in YYYY-MM-DD format. Null if unknown.",
                            },
                            "invoice_number": {"type": "string"},
                            "order_number": {"type": "string"},
                            "amount_tax_excl": {
                                "type": "number",
                                "description": "Amount excluding tax (HT). Null if unknown.",
                            },
                            "tax_amount": {
                                "type": "number",
                                "description": "Tax amount (TVA). Null if unknown.",
                            },
                            "tax_rate": {
                                "type": "number",
                                "description": "Tax rate as percentage (e.g. 20.00 for 20%). Null if unknown.",
                            },
                            "payment_method": {
                                "type": "string",
                                "description": "Payment method: CB, credit card, PayPal, bank transfer, etc.",
                            },
                            "payment_reference": {
                                "type": "string",
                                "description": "Payment reference or transaction ID from the payment processor.",
                            },
                            "items": {
                                "type": "array",
                                "description": "Line items if available.",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "quantity": {"type": "number"},
                                        "unit_price": {"type": "number"},
                                    },
                                    "required": ["name"],
                                },
                            },
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

EXTRACTION_SYSTEM_PROMPT = (
    "You are a financial data extractor. For each email provided, extract structured transaction data.\n\n"
    "EXTRACT these fields: vendor_name, amount (TTC/total including tax), currency (EUR/USD/GBP/etc.), "
    "transaction_date (YYYY-MM-DD), "
    "type (invoice/receipt/order/payment/shipping/refund/cancellation/subscription/other), "
    "invoice_number, order_number, description.\n\n"
    "Also extract if available (OPTIONAL — only extract what's actually in the email): "
    "amount excluding tax (amount_tax_excl), tax amount (tax_amount), tax rate percentage (tax_rate, e.g. 20.00 for 20%), "
    "payment method (payment_method: CB, credit card, PayPal, bank transfer, etc.), "
    "payment reference/transaction ID (payment_reference), "
    "and line items (items: list of {name, quantity, unit_price}).\n\n"
    "RULES:\n"
    "- If the snippet is empty or missing amounts/key details, use get_email_body to fetch the full content.\n"
    "- Set status='complete' if you have vendor + amount + date, otherwise 'partial'.\n"
    "- confidence: 0.0-1.0 for how sure you are this is a real transaction.\n"
    "- NEVER invent data. No amount found = null + status='partial'.\n"
    "- Prefer transaction date from email content over email send date.\n"
    "- Save each transaction with save_transactions.\n"
    "- Mark ALL emails as processed when done using mark_emails_processed.\n"
    "- Process every email in the batch."
)

EXTRACTION_TOOL_HANDLERS = {
    'get_email_body': _execute_get_email_body,
    'save_transactions': _execute_save_transactions,
    'mark_emails_processed': _execute_mark_emails_processed,
}


# --- Helpers ---

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


# ============================================================
# PASS 1 — TRIAGE
# ============================================================

TRIAGE_PROMPT = (
    "For each email below, determine if it is transactional or not.\n\n"
    "TRANSACTIONAL = invoice, receipt, order confirmation, payment confirmation, "
    "shipping notification, refund, cancellation, subscription charge/renewal.\n\n"
    "NOT TRANSACTIONAL = newsletter, notification, conversation, security alert, "
    "marketing, verification code, welcome email with no charge, account update, "
    "social media notification, promotional offer.\n\n"
    "Respond with ONLY a JSON array of objects, one per email:\n"
    '[{"id": <email_id>, "transactional": true/false}]\n\n'
    "No other text. Just the JSON array."
)


def _triage_single_batch(client, emails_data, rate_limiter):
    """
    Run triage on a single batch of emails.
    Returns (transactional_ids, ignored_ids).
    """
    # Build minimal email descriptions
    email_lines = []
    for e in emails_data:
        email_lines.append(
            f'- id={e["id"]}, from="{e["from_address"]}", subject="{e["subject"]}", '
            f'snippet="{e["snippet"][:120]}", date="{e["date"]}"'
        )
    emails_text = "\n".join(email_lines)

    user_msg = f"{TRIAGE_PROMPT}\nEmails ({len(emails_data)}):\n{emails_text}"

    if rate_limiter:
        rate_limiter.wait_if_needed()

    response = _call_api_with_retry(
        client,
        model=MODEL,
        max_tokens=2048,
        messages=[{"role": "user", "content": user_msg}],
    )

    if rate_limiter and hasattr(response, 'usage') and response.usage:
        rate_limiter.record_usage(response.usage.input_tokens)

    # Extract text response
    response_text = ""
    for block in response.content:
        if hasattr(block, 'text') and block.text:
            response_text += block.text

    # Parse JSON
    results = _extract_json(response_text)
    if results is None:
        logger.error(f'Triage: failed to parse JSON response: {response_text[:500]}')
        # Fail safe: treat all as transactional so they proceed to extraction
        return [e["id"] for e in emails_data], []

    transactional_ids = []
    ignored_ids = []

    # Build a set of valid email IDs for this batch
    valid_ids = {e["id"] for e in emails_data}

    for item in results:
        email_id = item.get("id")
        is_transactional = item.get("transactional", False)

        if email_id not in valid_ids:
            logger.warning(f'Triage: LLM returned unknown email id {email_id}, skipping')
            continue

        if is_transactional:
            transactional_ids.append(email_id)
        else:
            ignored_ids.append(email_id)

    # Any IDs from the batch not mentioned by the LLM — treat as transactional (safe default)
    mentioned_ids = set(transactional_ids) | set(ignored_ids)
    for e in emails_data:
        if e["id"] not in mentioned_ids:
            logger.warning(f'Triage: email {e["id"]} not in LLM response, treating as transactional')
            transactional_ids.append(e["id"])

    return transactional_ids, ignored_ids


def _process_triage_batch(api_key, emails_data, batch_num, total_batches, rate_limiter):
    """Process a single triage batch in its own thread. Returns (transactional_ids, ignored_ids)."""
    thread_id = threading.current_thread().name
    logger.info(
        f'[Triage] Batch {batch_num}/{total_batches} — {len(emails_data)} emails (thread-{thread_id})'
    )

    client = anthropic.Anthropic(api_key=api_key)

    try:
        transactional_ids, ignored_ids = _triage_single_batch(client, emails_data, rate_limiter)
        logger.info(
            f'[Triage] Batch {batch_num}/{total_batches} done — '
            f'{len(transactional_ids)} transactional, {len(ignored_ids)} ignored (thread-{thread_id})'
        )
        return transactional_ids, ignored_ids
    except Exception as e:
        logger.error(f'[Triage] Batch {batch_num} error (thread-{thread_id}): {e}')
        # Fail safe: treat all as transactional
        return [em["id"] for em in emails_data], []


def _run_triage_pass(user, api_key):
    """
    Pass 1: Triage — classify emails as transactional or not using fast batched LLM calls.
    Marks non-transactional as 'ignored', transactional as 'triage_passed'.
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
    all_batches = []
    for i in range(0, len(emails_data), TRIAGE_BATCH_SIZE):
        all_batches.append(emails_data[i:i + TRIAGE_BATCH_SIZE])

    total_batches = len(all_batches)
    logger.info(f'[Triage] {len(emails_data)} emails in {total_batches} batches (max {TRIAGE_MAX_CONCURRENT} concurrent)')

    rate_limiter = RateLimiter()

    all_transactional_ids = []
    all_ignored_ids = []

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
                transactional_ids, ignored_ids = future.result()
                all_transactional_ids.extend(transactional_ids)
                all_ignored_ids.extend(ignored_ids)
            except Exception as e:
                logger.error(f'[Triage] Batch {batch_num} raised unexpected exception: {e}')

    # Update statuses in DB
    if all_ignored_ids:
        Email.objects.filter(user=user, id__in=all_ignored_ids).update(
            status=Email.Status.IGNORED
        )
    if all_transactional_ids:
        Email.objects.filter(user=user, id__in=all_transactional_ids).update(
            status=Email.Status.TRIAGE_PASSED
        )

    logger.info(
        f'[Triage] === PASS 1 DONE === '
        f'{len(all_transactional_ids)} transactional, {len(all_ignored_ids)} ignored '
        f'out of {len(emails_data)}'
    )

    return {
        'triage_transactional': len(all_transactional_ids),
        'triage_ignored': len(all_ignored_ids),
        'triage_total': len(emails_data),
    }


# ============================================================
# PASS 2 — EXTRACTION
# ============================================================

def _extraction_single_batch(client, user, emails_data, batch_stats, rate_limiter):
    """
    Run extraction on a single batch of triage-passed emails using tool_use.
    Modifies batch_stats in place.
    """
    emails_text = json.dumps(emails_data, default=str, ensure_ascii=False)

    user_msg = (
        f"Extract transaction data from these {len(emails_data)} transactional emails.\n"
        f"For each email, extract: vendor_name, amount, currency, transaction_date, type, "
        f"invoice_number, order_number, description. "
        f"Also extract if present: amount_tax_excl, tax_amount, tax_rate, payment_method, payment_reference, items.\n"
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
        model=MODEL,
        max_tokens=4096,
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

        # Log thinking
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

                logger.info(f'  [Extraction] TOOL: {tool_name}({json.dumps(tool_input, default=str)[:300]})')

                handler = EXTRACTION_TOOL_HANDLERS.get(tool_name)
                if handler:
                    try:
                        result = handler(user, tool_input)
                        logger.info(
                            f'  [Extraction] RESULT: {tool_name} -> {json.dumps(result, default=str)[:300]}'
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
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

        if rate_limiter:
            rate_limiter.wait_if_needed()

        response = _call_api_with_retry(
            client,
            model=MODEL,
            max_tokens=4096,
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
        f'[Extraction] Batch {batch_num}/{total_batches} — {len(emails_data)} emails (thread-{thread_id})'
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
        logger.warning(f'[Extraction] Rate limited on batch {batch_num} (thread-{thread_id}), waiting 60s...')
        time.sleep(60)
        try:
            _extraction_single_batch(client, user, emails_data, batch_stats, rate_limiter)
        except Exception as e:
            logger.error(f'[Extraction] Batch {batch_num} failed after retry (thread-{thread_id}): {e}')
            batch_stats["errors"] += 1
    except Exception as e:
        logger.error(f'[Extraction] Batch {batch_num} error (thread-{thread_id}): {e}')
        batch_stats["errors"] += 1

    logger.info(
        f'[Extraction] Batch {batch_num}/{total_batches} done — '
        f'created={batch_stats["transactions_created"]}, '
        f'updated={batch_stats["transactions_updated"]}, '
        f'processed={batch_stats["emails_processed"]} (thread-{thread_id})'
    )
    return batch_stats


def _run_extraction_pass(user, api_key):
    """
    Pass 2: Extraction — extract structured transaction data from triage-passed emails.
    Uses tool_use with get_email_body, save_transactions, mark_emails_processed.
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
    all_batches = []
    for i in range(0, len(emails_data_all), EXTRACTION_BATCH_SIZE):
        all_batches.append(emails_data_all[i:i + EXTRACTION_BATCH_SIZE])

    total_batches = len(all_batches)
    logger.info(
        f'[Extraction] {len(emails_data_all)} emails in {total_batches} batches '
        f'(max {EXTRACTION_MAX_CONCURRENT} concurrent)'
    )

    rate_limiter = RateLimiter()

    stats = {
        'extraction_transactions_created': 0,
        'extraction_transactions_updated': 0,
        'extraction_emails_processed': 0,
        'extraction_emails_ignored': 0,
        'extraction_api_calls': 0,
        'extraction_errors': 0,
    }
    stats_lock = threading.Lock()

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
# PASS 3 — CORRELATION
# ============================================================

CORRELATION_PROMPT_TEMPLATE = (
    "Here are {count} transactions from vendor \"{vendor}\".\n"
    "Some may be duplicates or related (e.g., order + shipping + delivery = same purchase, "
    "or a receipt and payment confirmation for the same charge).\n\n"
    "Return a JSON array of merge instructions:\n"
    '[{{"keep_id": <id_to_keep>, "delete_id": <id_to_remove>, "reason": "explanation"}}]\n\n'
    "If all transactions are distinct and should NOT be merged, return an empty array: []\n\n"
    "Only merge when you are confident they represent the same underlying purchase/charge. "
    "Different amounts on different dates = distinct transactions, do NOT merge.\n\n"
    "Transactions:\n{transactions_json}"
)


def _run_correlation_pass(user, api_key):
    """
    Pass 3: Correlation — find and merge duplicate/related transactions per vendor.
    Uses plain JSON responses (no tool_use).
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
    rate_limiter = RateLimiter()

    total_merges = 0
    vendors_checked = 0

    for vendor_name, txs in multi_groups.items():
        vendors_checked += 1

        # Build transaction data for the LLM
        tx_data = []
        for tx in txs:
            tx_data.append({
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
            })

        prompt = CORRELATION_PROMPT_TEMPLATE.format(
            count=len(txs),
            vendor=vendor_name,
            transactions_json=json.dumps(tx_data, ensure_ascii=False, indent=2),
        )

        if rate_limiter:
            rate_limiter.wait_if_needed()

        try:
            response = _call_api_with_retry(
                client,
                model=MODEL,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )

            if rate_limiter and hasattr(response, 'usage') and response.usage:
                rate_limiter.record_usage(response.usage.input_tokens)

        except Exception as e:
            logger.error(f'[Correlation] API error for vendor "{vendor_name}": {e}')
            continue

        # Extract response text
        response_text = ""
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                response_text += block.text

        merge_instructions = _extract_json(response_text)
        if merge_instructions is None:
            logger.warning(
                f'[Correlation] Could not parse JSON for vendor "{vendor_name}": {response_text[:300]}'
            )
            continue

        if not merge_instructions:
            logger.info(f'[Correlation] Vendor "{vendor_name}": all {len(txs)} transactions are distinct')
            continue

        # Build a lookup of transaction objects by ID
        tx_by_id = {tx.id: tx for tx in txs}

        # Execute merge instructions
        deleted_ids = set()
        for instruction in merge_instructions:
            keep_id = instruction.get('keep_id')
            delete_id = instruction.get('delete_id')
            reason = instruction.get('reason', 'LLM correlation')

            if keep_id is None or delete_id is None:
                logger.warning(f'[Correlation] Invalid merge instruction: {instruction}')
                continue

            if delete_id in deleted_ids:
                logger.info(f'[Correlation] Transaction {delete_id} already deleted, skipping')
                continue

            keep_tx = tx_by_id.get(keep_id)
            delete_tx = tx_by_id.get(delete_id)

            if not keep_tx or not delete_tx:
                logger.warning(
                    f'[Correlation] Transaction not found: keep={keep_id}, delete={delete_id}'
                )
                continue

            if keep_id in deleted_ids:
                logger.warning(
                    f'[Correlation] Cannot keep transaction {keep_id} — already deleted'
                )
                continue

            # Merge: keep the richer one, absorb data from the other
            logger.info(
                f'[Correlation] Merging transaction {delete_id} into {keep_id} '
                f'for vendor "{vendor_name}": {reason}'
            )

            # Absorb fields from delete_tx into keep_tx
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

    logger.info(
        f'[Correlation] === PASS 3 DONE === '
        f'{total_merges} merges across {vendors_checked} vendors'
    )

    return {
        'correlation_merges': total_merges,
        'correlation_vendors_checked': vendors_checked,
    }


# ============================================================
# MAIN PIPELINE
# ============================================================

def run_pipeline(user):
    """
    Run the full multi-pass email classification pipeline.

    1. Prefilter (rule-based)
    2. Triage (fast LLM pass — transactional yes/no)
    3. Extraction (detailed LLM pass — extract transaction data with tool_use)
    4. Correlation (LLM pass — merge related transactions per vendor)

    Returns a combined stats dict.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    logger.info('====== PIPELINE START ======')

    # Step 1: Prefilter
    prefilter_stats = prefilter_emails(user)
    logger.info(
        f'[Prefilter] {prefilter_stats["auto_ignored"]} auto-ignored, '
        f'{prefilter_stats["remaining_for_ai"]} remaining for AI'
    )

    # Step 2: Triage
    triage_stats = _run_triage_pass(user, api_key)

    # Step 3: Extraction
    extraction_stats = _run_extraction_pass(user, api_key)

    # Step 4: Correlation
    correlation_stats = _run_correlation_pass(user, api_key)

    # Combine all stats
    stats = {
        'prefilter_auto_ignored': prefilter_stats['auto_ignored'],
        'prefilter_remaining': prefilter_stats['remaining_for_ai'],
        **triage_stats,
        **extraction_stats,
        **correlation_stats,
    }

    logger.info(f'====== PIPELINE DONE ====== Stats: {json.dumps(stats)}')

    return stats
