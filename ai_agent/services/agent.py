import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal, InvalidOperation

import anthropic
import requests
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.conf import settings
from django.utils import timezone

from emails.models import Email, Transaction
from emails.services.merge import merge_related_transactions
from emails.services.token_refresh import get_valid_token

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open and calls are blocked."""
    pass


class CircuitBreaker:
    """Stops API calls after consecutive failures to avoid burning budget."""
    CLOSED = 'closed'
    OPEN = 'open'
    HALF_OPEN = 'half_open'

    def __init__(self, failure_threshold=3, recovery_timeout=60):
        self.state = self.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = None
        self._lock = threading.Lock()

    def can_call(self):
        with self._lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if time.time() - self.last_failure_time >= self.recovery_timeout:
                    self.state = self.HALF_OPEN
                    return True
                return False
            if self.state == self.HALF_OPEN:
                return True
            return False

    def record_success(self):
        with self._lock:
            self.failure_count = 0
            self.state = self.CLOSED

    def record_failure(self):
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.time()
            if self.failure_count >= self.failure_threshold:
                self.state = self.OPEN
                logger.warning(
                    f'[CircuitBreaker] OPEN — {self.failure_count} consecutive failures, '
                    f'blocking calls for {self.recovery_timeout}s'
                )


BATCH_SIZE = 25  # Emails per LLM batch (increased — most batches are all-ignored)
MAX_RETRIES = settings.AI_MAX_RETRIES
RETRY_BASE_DELAY = settings.AI_RETRY_BASE_DELAY
MAX_CONCURRENT_BATCHES = settings.AI_TRIAGE_MAX_CONCURRENT
RATE_LIMIT_INPUT_TOKENS = settings.AI_RATE_LIMIT_TOKENS_PER_MIN

# --- Tool definitions for Claude ---

TOOLS = [
    {
        "name": "list_emails",
        "description": (
            "List emails from the database. Use this to see what emails need processing. "
            "Returns email id, from_address, from_name, subject, snippet, date, has_attachments, and status."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": ["new", "processed", "ignored"],
                    "description": "Filter by status. Default: 'new' to see unprocessed emails.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max number of emails to return. Default: 20.",
                },
                "offset": {
                    "type": "integer",
                    "description": "Offset for pagination. Default: 0.",
                },
            },
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
    {
        "name": "search_transactions",
        "description": (
            "Search existing transactions in the database for correlation. "
            "Use this to check if a transaction already exists or to find related transactions. "
            "Vendor name search is fuzzy (strips Inc/Ltd/SAS/etc and ignores case)."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_name": {
                    "type": "string",
                    "description": "Search by vendor name (fuzzy match: case-insensitive, strips common suffixes like Inc/Ltd/SAS).",
                },
                "order_number": {
                    "type": "string",
                    "description": "Search by order number.",
                },
                "invoice_number": {
                    "type": "string",
                    "description": "Search by invoice number.",
                },
                "email_id": {
                    "type": "integer",
                    "description": "Search by source email database ID.",
                },
                "amount": {
                    "type": "number",
                    "description": "Search by exact transaction amount.",
                },
                "date_range": {
                    "type": "object",
                    "properties": {
                        "from": {
                            "type": "string",
                            "description": "Start date in YYYY-MM-DD format (inclusive).",
                        },
                        "to": {
                            "type": "string",
                            "description": "End date in YYYY-MM-DD format (inclusive).",
                        },
                    },
                    "description": "Filter by transaction date range.",
                },
                "status": {
                    "type": "string",
                    "enum": ["partial", "complete"],
                    "description": "Filter by transaction status.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max results. Default: 10.",
                },
            },
        },
    },
]

SYSTEM_PROMPT = """You classify emails as transactional or not, and extract transaction data.

CORE RULE — ONE TRANSACTION PER PURCHASE:
- ALWAYS search_transactions by vendor/order/invoice BEFORE saving. If a match exists, save with the same order_number so it gets merged — do NOT create a new transaction.
- A shipping email for an existing order? Search for the existing order and mark the shipping email as processed. Do NOT create a separate shipping transaction.
- A receipt and a payment notification for the same amount, same vendor, same date = SAME transaction. Save only once.
- Carrier emails (DHL/FedEx/UPS, etc.) — the vendor is whoever shipped the package, not the carrier. Search by order/tracking number to find the real vendor's transaction.

WHAT TO IGNORE (mark as 'ignored'):
- Newsletters, marketing, promotions, security alerts, verification codes, conversations
- Subscription welcome emails with no amount — NOT transactions

DATA EXTRACTION:
- Extract: vendor_name, amount, currency (ISO 4217 code), transaction_date (YYYY-MM-DD), invoice_number, order_number, type, description
- Currency: extract from email content. If not found, leave empty.
- status='complete' if vendor + amount + date are known, otherwise 'partial'
- confidence: 0.0-1.0 for how sure you are it's a real transaction
- NEVER invent data. No amount found = null + status='partial'
- Prefer transaction date from email content over email send date

EMPTY SNIPPETS:
- If snippet is empty/blank but subject suggests a transaction (order, shipped, etc.), ALWAYS use get_email_body first

EFFICIENCY:
- Process ALL emails in the batch. Group ignored emails in a single mark_emails_processed call."""


# --- Tool execution ---

def _execute_list_emails(user, params):
    status = params.get('status', 'new')
    limit = min(params.get('limit', 20), 50)
    offset = params.get('offset', 0)

    emails = Email.objects.filter(user=user, status=status).order_by('-date')[offset:offset + limit]
    return [
        {
            'id': e.id,
            'from_address': e.from_address,
            'from_name': e.from_name,
            'subject': e.subject,
            'snippet': e.snippet,
            'date': e.date.isoformat(),
            'has_attachments': e.has_attachments,
            'provider': e.provider,
        }
        for e in emails
    ]


def _fetch_gmail_body(email_obj):
    """Fetch email body from Gmail API."""
    import base64

    access_token = get_valid_token(email_obj.user, 'google')
    if not access_token:
        return "Error: no Google token available"

    resp = requests.get(
        f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_obj.message_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'format': 'full'},
    )
    if resp.status_code != 200:
        return f"Error fetching email: {resp.status_code}"

    data = resp.json()
    payload = data.get('payload', {})

    def find_part(payload, mime_type):
        """Recursively find a part by MIME type."""
        if payload.get('mimeType') == mime_type:
            body_data = payload.get('body', {}).get('data', '')
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
        for part in payload.get('parts', []):
            result = find_part(part, mime_type)
            if result:
                return result
        return None

    # Try text/plain first, fallback to text/html
    text = find_part(payload, 'text/plain')
    if text and text.strip():
        return text[:settings.AI_EMAIL_BODY_MAX_CHARS]

    # Fallback: extract text from HTML
    html = find_part(payload, 'text/html')
    if html:
        import re
        # Remove style/script blocks first
        html = re.sub(r'<(style|script)[^>]*>.*?</\1>', ' ', html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:settings.AI_EMAIL_BODY_MAX_CHARS]

    return "No text content found in email."


def _fetch_microsoft_body(email_obj):
    """Fetch email body from Microsoft Graph API."""
    access_token = get_valid_token(email_obj.user, 'microsoft')
    if not access_token:
        return "Error: no Microsoft token available"

    resp = requests.get(
        f'https://graph.microsoft.com/v1.0/me/messages/{email_obj.message_id}',
        headers={'Authorization': f'Bearer {access_token}'},
        params={'$select': 'body'},
    )
    if resp.status_code != 200:
        return f"Error fetching email: {resp.status_code}"

    data = resp.json()
    body = data.get('body', {})
    content = body.get('content', '')

    # Strip HTML tags roughly if HTML
    if body.get('contentType') == 'html':
        import re
        content = re.sub(r'<[^>]+>', ' ', content)
        content = re.sub(r'\s+', ' ', content).strip()

    return content[:settings.AI_EMAIL_BODY_MAX_CHARS]


def _execute_get_email_body(user, params):
    email_id = params.get('email_id')
    try:
        email_obj = Email.objects.get(id=email_id, user=user)
    except Email.DoesNotExist:
        return {"error": f"Email {email_id} not found"}

    # If body is already stored in DB (test emails or cached), return it directly
    if email_obj.body:
        return {"email_id": email_id, "body": email_obj.body}

    if email_obj.provider == 'google':
        body = _fetch_gmail_body(email_obj)
    elif email_obj.provider == 'microsoft':
        body = _fetch_microsoft_body(email_obj)
    else:
        body = "Unknown provider"

    return {"email_id": email_id, "body": body}


def _normalize_vendor_name(name):
    """Normalize vendor name for fuzzy comparison: lowercase, strip common suffixes."""
    import re
    if not name:
        return ''
    name = name.strip().lower()
    # Strip common corporate suffixes
    name = re.sub(
        r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sa\.?|gmbh\.?|co\.?|corp\.?|limited|pty\.?)\s*$',
        '', name, flags=re.IGNORECASE,
    )
    # Strip trailing commas and whitespace left after suffix removal
    name = name.strip(' ,')
    # Collapse whitespace
    name = re.sub(r'\s+', ' ', name).strip()
    return name


def _find_existing_transaction(user, email_obj, tx_data, amount, tx_date):
    """
    Find an existing transaction matching ANY of these criteria (checked in order):
    1. Same email_id (source email)
    2. Same order_number (if not empty)
    3. Same invoice_number (if not empty)
    4. Same vendor_name (normalized) + same amount + same date
    Returns the first match or None.
    """
    # 1. Same source email
    if email_obj:
        match = Transaction.objects.filter(user=user, email=email_obj).first()
        if match:
            return match

    # 2. Same order_number
    order_number = (tx_data.get('order_number') or '').strip()
    if order_number:
        match = Transaction.objects.filter(user=user, order_number=order_number).first()
        if match:
            return match

    # 3. Same invoice_number
    invoice_number = (tx_data.get('invoice_number') or '').strip()
    if invoice_number:
        match = Transaction.objects.filter(user=user, invoice_number=invoice_number).first()
        if match:
            return match

    # 4. Same vendor (normalized) + same amount + same date
    vendor_name = tx_data.get('vendor_name', '')
    normalized = _normalize_vendor_name(vendor_name)
    if normalized and amount is not None and tx_date:
        candidates = Transaction.objects.filter(
            user=user, amount=amount, transaction_date=tx_date,
        )
        for candidate in candidates:
            if _normalize_vendor_name(candidate.vendor_name) == normalized:
                return candidate

    return None


def _merge_transaction(existing, tx_data, email_obj, amount, tx_date):
    """
    Merge new data into an existing transaction, keeping the most complete version.
    - Merges raw_data dicts
    - Keeps the highest confidence
    - Upgrades status from partial to complete if new data fills missing fields
    """
    existing.type = tx_data.get('type', existing.type)
    existing.vendor_name = tx_data.get('vendor_name') or existing.vendor_name

    # Keep the most informative amount (prefer non-null)
    if amount is not None:
        existing.amount = amount
    existing.currency = tx_data.get('currency') or existing.currency or ''

    # Keep the most informative date (prefer non-null)
    if tx_date:
        existing.transaction_date = tx_date

    # Merge string fields: keep whichever is non-empty, prefer new data if both exist
    existing.invoice_number = tx_data.get('invoice_number') or existing.invoice_number or ''
    existing.order_number = tx_data.get('order_number') or existing.order_number or ''
    existing.description = tx_data.get('description') or existing.description or ''
    existing.payment_method = tx_data.get('payment_method') or existing.payment_method or ''
    existing.payment_reference = tx_data.get('payment_reference') or existing.payment_reference or ''

    # Merge optional decimal fields (prefer non-null new data)
    for field in ('amount_tax_excl', 'tax_amount', 'tax_rate'):
        if tx_data.get(field) is not None:
            try:
                setattr(existing, field, Decimal(str(tx_data[field])))
            except (InvalidOperation, ValueError):
                pass

    # Merge items (prefer non-empty new data)
    new_items = tx_data.get('items')
    if new_items:
        existing.items = new_items

    # Keep the highest confidence
    new_confidence = tx_data.get('confidence', 0.0)
    existing.confidence = max(existing.confidence, new_confidence)

    # Upgrade status from partial to complete if new data fills missing fields
    new_status = tx_data.get('status', existing.status)
    if existing.status == 'partial' and new_status == 'complete':
        existing.status = 'complete'
    elif existing.status == 'complete':
        pass  # Don't downgrade
    else:
        existing.status = new_status

    # Link the new email too (keep the original, but update if none was set)
    if email_obj and not existing.email:
        existing.email = email_obj

    # Merge raw_data dicts
    merged_raw = existing.raw_data.copy() if isinstance(existing.raw_data, dict) else {}
    merged_raw.update(tx_data)
    existing.raw_data = merged_raw

    existing.save()


def _execute_save_transactions(user, params):
    transactions_data = params.get('transactions', [])
    created = 0
    updated = 0

    for tx_data in transactions_data:
        email_id = tx_data.get('email_id')
        email_obj = None
        if email_id:
            try:
                email_obj = Email.objects.get(id=email_id, user=user)
            except Email.DoesNotExist:
                pass

        # Parse amount safely
        amount = None
        if tx_data.get('amount') is not None:
            try:
                amount = Decimal(str(tx_data['amount']))
            except (InvalidOperation, ValueError):
                pass

        # Parse optional decimal fields
        amount_tax_excl = None
        if tx_data.get('amount_tax_excl') is not None:
            try:
                amount_tax_excl = Decimal(str(tx_data['amount_tax_excl']))
            except (InvalidOperation, ValueError):
                pass

        tax_amount = None
        if tx_data.get('tax_amount') is not None:
            try:
                tax_amount = Decimal(str(tx_data['tax_amount']))
            except (InvalidOperation, ValueError):
                pass

        tax_rate = None
        if tx_data.get('tax_rate') is not None:
            try:
                tax_rate = Decimal(str(tx_data['tax_rate']))
            except (InvalidOperation, ValueError):
                pass

        # Parse date safely
        tx_date = None
        if tx_data.get('transaction_date'):
            try:
                from datetime import date
                tx_date = date.fromisoformat(tx_data['transaction_date'])
            except ValueError:
                pass

        # Find existing transaction using multi-criteria dedup
        existing = _find_existing_transaction(user, email_obj, tx_data, amount, tx_date)

        if existing:
            _merge_transaction(existing, tx_data, email_obj, amount, tx_date)
            updated += 1
        else:
            Transaction.objects.create(
                user=user,
                email=email_obj,
                type=tx_data.get('type', 'other'),
                vendor_name=tx_data.get('vendor_name', 'Unknown'),
                amount=amount,
                currency=tx_data.get('currency', '') or '',
                transaction_date=tx_date,
                invoice_number=tx_data.get('invoice_number', '') or '',
                order_number=tx_data.get('order_number', '') or '',
                amount_tax_excl=amount_tax_excl,
                tax_amount=tax_amount,
                tax_rate=tax_rate,
                payment_method=tx_data.get('payment_method', '') or '',
                payment_reference=tx_data.get('payment_reference', '') or '',
                items=tx_data.get('items', []) or [],
                description=tx_data.get('description', '') or '',
                confidence=tx_data.get('confidence', 0.0),
                status=tx_data.get('status', 'partial'),
                raw_data=tx_data,
            )
            created += 1

    return {"created": created, "updated": updated}


def _execute_mark_emails_processed(user, params):
    email_ids = params.get('email_ids', [])
    new_status = params.get('status', 'processed')
    count = Email.objects.filter(user=user, id__in=email_ids).update(status=new_status)
    return {"marked": count, "status": new_status}


def _execute_search_transactions(user, params):
    import re
    from datetime import date as date_type

    qs = Transaction.objects.filter(user=user)

    # Fuzzy vendor name search: normalize and match against all transactions
    if params.get('vendor_name'):
        search_name = params['vendor_name'].strip().lower()
        # Strip common corporate suffixes from search term
        search_name_normalized = re.sub(
            r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sa\.?|gmbh\.?|co\.?|corp\.?|limited|pty\.?)\s*$',
            '', search_name, flags=re.IGNORECASE,
        ).strip()
        # Use icontains on the core name for DB-level filtering, then refine in Python
        if search_name_normalized:
            qs = qs.filter(vendor_name__icontains=search_name_normalized)

    if params.get('order_number'):
        qs = qs.filter(order_number=params['order_number'])
    if params.get('invoice_number'):
        qs = qs.filter(invoice_number=params['invoice_number'])
    if params.get('email_id'):
        qs = qs.filter(email_id=params['email_id'])
    if params.get('amount') is not None:
        try:
            amount_val = Decimal(str(params['amount']))
            qs = qs.filter(amount=amount_val)
        except (InvalidOperation, ValueError):
            pass
    if params.get('date_range'):
        date_range = params['date_range']
        if date_range.get('from'):
            try:
                from_date = date_type.fromisoformat(date_range['from'])
                qs = qs.filter(transaction_date__gte=from_date)
            except ValueError:
                pass
        if date_range.get('to'):
            try:
                to_date = date_type.fromisoformat(date_range['to'])
                qs = qs.filter(transaction_date__lte=to_date)
            except ValueError:
                pass
    if params.get('status'):
        qs = qs.filter(status=params['status'])

    limit = min(params.get('limit', 10), 50)
    results = qs[:limit]

    return [
        {
            'id': t.id,
            'type': t.type,
            'vendor_name': t.vendor_name,
            'amount': str(t.amount) if t.amount else None,
            'currency': t.currency,
            'transaction_date': t.transaction_date.isoformat() if t.transaction_date else None,
            'invoice_number': t.invoice_number,
            'order_number': t.order_number,
            'description': t.description,
            'status': t.status,
            'email_id': t.email_id,
        }
        for t in results
    ]


TOOL_HANDLERS = {
    'list_emails': _execute_list_emails,
    'get_email_body': _execute_get_email_body,
    'save_transactions': _execute_save_transactions,
    'mark_emails_processed': _execute_mark_emails_processed,
    'search_transactions': _execute_search_transactions,
}


# --- Rate limiter ---

class RateLimiter:
    """Thread-safe rate limiter that tracks input tokens per minute."""

    def __init__(self, max_tokens_per_minute=RATE_LIMIT_INPUT_TOKENS):
        self.max_tokens_per_minute = max_tokens_per_minute
        self._lock = threading.Lock()
        self._tokens_used = []  # list of (timestamp, token_count)

    def record_usage(self, input_tokens):
        """Record token usage from an API response."""
        with self._lock:
            self._tokens_used.append((time.monotonic(), input_tokens))

    def _purge_old_entries(self):
        """Remove entries older than 60 seconds. Must be called with lock held."""
        cutoff = time.monotonic() - 60
        self._tokens_used = [(ts, count) for ts, count in self._tokens_used if ts > cutoff]

    def _current_usage(self):
        """Get tokens used in the last 60 seconds. Must be called with lock held."""
        self._purge_old_entries()
        return sum(count for _, count in self._tokens_used)

    def wait_if_needed(self):
        """Block until we have headroom under the rate limit."""
        while True:
            with self._lock:
                self._purge_old_entries()
                current = sum(count for _, count in self._tokens_used)
                if current < self.max_tokens_per_minute:
                    return
                # Calculate how long until enough tokens expire
                if self._tokens_used:
                    oldest_ts = self._tokens_used[0][0]
                    wait_time = 60 - (time.monotonic() - oldest_ts) + 0.5
                else:
                    wait_time = 1.0
            logger.warning(
                f'Rate limiter: {current}/{self.max_tokens_per_minute} tokens used in last 60s, '
                f'sleeping {wait_time:.1f}s'
            )
            time.sleep(max(wait_time, 0.5))


# --- Agent orchestration ---

def _call_api_with_retry(client, **kwargs):
    """Call Anthropic API with retry on rate limit errors."""
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


def _get_existing_transactions_summary(user):
    """Build a short summary of existing transactions for the agent context."""
    txs = Transaction.objects.filter(user=user).order_by('-transaction_date')[:50]
    if not txs:
        return ""
    summary = []
    for t in txs:
        amt = str(t.amount) if t.amount else '?'
        summary.append({
            'id': t.id,
            'vendor': t.vendor_name,
            'type': t.type,
            'amount': amt,
            'currency': t.currency,
            'date': str(t.transaction_date) if t.transaction_date else '?',
            'order': t.order_number or '',
            'invoice': t.invoice_number or '',
            'status': t.status,
        })
    return json.dumps(summary, ensure_ascii=False)


def _run_agent_on_batch(client, user, emails_data, batch_stats, rate_limiter=None):
    """
    Run a single agent session on a small batch of emails.
    Fresh context each time to avoid token accumulation.
    Each thread should pass its own Anthropic client instance.
    batch_stats is a local dict for this batch (aggregated by caller).
    """
    emails_text = json.dumps(emails_data, default=str, ensure_ascii=False)

    # Give the agent context about existing transactions so it can correlate
    existing_txs = _get_existing_transactions_summary(user)
    context_block = ""
    if existing_txs:
        context_block = (
            f"\n\nEXISTING TRANSACTIONS (already saved — update these instead of creating duplicates):\n"
            f"{existing_txs}\n"
        )

    user_msg = (
        f"Classify these {len(emails_data)} emails. For each:\n"
        f"- If transactional: save_transactions (or update existing), then mark as 'processed'\n"
        f"- If not transactional: mark as 'ignored'\n"
        f"- IMPORTANT: Check the existing transactions below. If an email relates to an existing transaction "
        f"(same vendor, same order, same amount+date), UPDATE it — do NOT create a duplicate.\n"
        f"- Process every email.\n"
        f"{context_block}\n"
        f"Emails:\n{emails_text}"
    )

    messages = [{"role": "user", "content": user_msg}]

    if rate_limiter:
        rate_limiter.wait_if_needed()

    response = _call_api_with_retry(
        client,
        model=settings.AI_MODEL_TRIAGE,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=messages,
    )
    batch_stats["api_calls"] += 1

    # Record token usage for rate limiting
    if rate_limiter and hasattr(response, 'usage') and response.usage:
        rate_limiter.record_usage(response.usage.input_tokens)

    # Agentic loop for this batch
    max_iterations = 15
    iteration = 0

    while iteration < max_iterations:
        iteration += 1
        logger.info(f'  Batch iteration {iteration} | stop_reason={response.stop_reason}')

        # Log thinking
        for block in response.content:
            if hasattr(block, 'text') and block.text:
                logger.info(f'  Agent thinking: {block.text[:300]}')

        if response.stop_reason != "tool_use":
            break

        tool_results = []
        assistant_content = response.content

        for block in assistant_content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                logger.info(f'  TOOL CALL: {tool_name}({json.dumps(tool_input, default=str)[:300]})')

                handler = TOOL_HANDLERS.get(tool_name)
                is_error = False
                if handler:
                    try:
                        result = handler(user, tool_input)
                        logger.info(f'  TOOL RESULT: {tool_name} -> {json.dumps(result, default=str)[:300]}')

                        if tool_name == 'save_transactions':
                            batch_stats["transactions_created"] += result.get("created", 0)
                            batch_stats["transactions_updated"] += result.get("updated", 0)
                            logger.info(f'    +{result.get("created", 0)} created, +{result.get("updated", 0)} updated')
                        elif tool_name == 'mark_emails_processed':
                            if tool_input.get('status') == 'processed':
                                batch_stats["emails_processed"] += result.get("marked", 0)
                            elif tool_input.get('status') == 'ignored':
                                batch_stats["emails_ignored"] += result.get("marked", 0)
                            logger.info(f'    Marked {result.get("marked", 0)} as {tool_input.get("status")}')

                    except Exception as e:
                        logger.error(f'  TOOL ERROR: {tool_name}: {e}')
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
            model=settings.AI_MODEL_TRIAGE,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        batch_stats["api_calls"] += 1

        # Record token usage for rate limiting
        if rate_limiter and hasattr(response, 'usage') and response.usage:
            rate_limiter.record_usage(response.usage.input_tokens)


def _process_single_batch(api_key, user, batch_data, batch_num, total_batches, rate_limiter):
    """
    Process a single batch in its own thread with its own Anthropic client.
    Returns a batch_stats dict.
    """
    thread_id = threading.current_thread().name
    logger.info(f'=== BATCH {batch_num}/{total_batches} === ({len(batch_data)} emails) (thread-{thread_id})')

    # Each thread gets its own Anthropic client instance
    client = anthropic.Anthropic(api_key=api_key)

    batch_stats = {
        "transactions_created": 0,
        "transactions_updated": 0,
        "emails_processed": 0,
        "emails_ignored": 0,
        "api_calls": 0,
        "batches": 0,
        "errors": 0,
    }

    try:
        _run_agent_on_batch(client, user, batch_data, batch_stats, rate_limiter=rate_limiter)
        batch_stats["batches"] += 1
    except anthropic.RateLimitError:
        logger.warning(f'Rate limited on batch {batch_num} (thread-{thread_id}), waiting 60s before retry...')
        time.sleep(60)
        try:
            _run_agent_on_batch(client, user, batch_data, batch_stats, rate_limiter=rate_limiter)
            batch_stats["batches"] += 1
        except Exception as e:
            logger.error(f'Batch {batch_num} failed after retry (thread-{thread_id}): {e}')
            batch_stats["errors"] += 1
    except Exception as e:
        logger.error(f'Batch {batch_num} error (thread-{thread_id}): {e}')
        batch_stats["errors"] += 1

    logger.info(f'Batch {batch_num}/{total_batches} completed (thread-{thread_id})')
    return batch_stats


def classify_emails(user):
    """
    Run the Claude agent to classify emails and extract transactions.
    Processes in parallel batches with rate limiting.
    Returns stats dict.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    # Check there are emails to process
    new_emails = list(
        Email.objects.filter(user=user, status=Email.Status.NEW)
        .order_by('-date')
        .values('id', 'from_address', 'from_name', 'subject', 'snippet', 'date', 'has_attachments', 'provider')
    )

    if not new_emails:
        return {
            "message": "No emails to process",
            "processed": 0,
        }

    stats = {
        "transactions_created": 0,
        "transactions_updated": 0,
        "emails_processed": 0,
        "emails_ignored": 0,
        "api_calls": 0,
        "batches": 0,
        "errors": 0,
        "total_emails": len(new_emails),
    }
    stats_lock = threading.Lock()

    # Prepare all batches
    all_batches = []
    for i in range(0, len(new_emails), BATCH_SIZE):
        batch = new_emails[i:i + BATCH_SIZE]
        batch_data = []
        for e in batch:
            batch_data.append({
                'id': e['id'],
                'from_address': e['from_address'],
                'from_name': e['from_name'],
                'subject': e['subject'],
                'snippet': e['snippet'],
                'date': e['date'].isoformat() if e['date'] else '',
                'has_attachments': e['has_attachments'],
            })
        all_batches.append(batch_data)

    total_batches = len(all_batches)

    logger.info(f'=== AGENT START === {len(new_emails)} new emails to classify')
    logger.info(f'Starting parallel processing: {total_batches} batches, max {MAX_CONCURRENT_BATCHES} concurrent')

    rate_limiter = RateLimiter(max_tokens_per_minute=RATE_LIMIT_INPUT_TOKENS)

    def _aggregate_stats(batch_stats):
        """Thread-safe aggregation of batch stats into global stats."""
        with stats_lock:
            for key in ("transactions_created", "transactions_updated",
                        "emails_processed", "emails_ignored",
                        "api_calls", "batches", "errors"):
                stats[key] += batch_stats.get(key, 0)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT_BATCHES) as executor:
        futures = {}
        for batch_idx, batch_data in enumerate(all_batches):
            batch_num = batch_idx + 1

            # Stagger batch launches by 1 second
            if batch_idx > 0:
                time.sleep(1)

            future = executor.submit(
                _process_single_batch,
                api_key, user, batch_data, batch_num, total_batches, rate_limiter,
            )
            futures[future] = batch_num

        # Collect results as they complete
        for future in as_completed(futures):
            batch_num = futures[future]
            try:
                batch_stats = future.result()
                _aggregate_stats(batch_stats)
            except Exception as e:
                logger.error(f'Batch {batch_num} raised unexpected exception: {e}')
                with stats_lock:
                    stats["errors"] += 1

    logger.info(f'=== AGENT DONE === batches: {stats["batches"]}, API calls: {stats["api_calls"]}, '
                f'transactions created: {stats["transactions_created"]}, '
                f'updated: {stats["transactions_updated"]}, '
                f'emails processed: {stats["emails_processed"]}, '
                f'ignored: {stats["emails_ignored"]}')

    # Post-processing: merge duplicate/fragmented transactions
    merge_stats = merge_related_transactions(user)
    stats["merge_merged"] = merge_stats["merged"]
    stats["merge_remaining"] = merge_stats["remaining"]

    return stats
