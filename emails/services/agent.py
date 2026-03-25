import json
import logging
import time
from decimal import Decimal, InvalidOperation

import anthropic
import requests
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.conf import settings
from django.utils import timezone

from emails.models import Email, Transaction

logger = logging.getLogger(__name__)

BATCH_SIZE = 15  # Emails per LLM batch
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2  # seconds

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
                                         "shipping", "refund", "subscription", "other"],
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
            "Use this to check if a transaction already exists or to find related transactions."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "vendor_name": {
                    "type": "string",
                    "description": "Search by vendor name (partial match).",
                },
                "order_number": {
                    "type": "string",
                    "description": "Search by order number.",
                },
                "invoice_number": {
                    "type": "string",
                    "description": "Search by invoice number.",
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

SYSTEM_PROMPT = """You are a financial email classifier and data extractor for a business accounting tool.

Your job:
1. Analyze email metadata (from, subject, snippet, date) to identify transactional emails
2. Transactional emails include: invoices, receipts, orders, payments, shipping confirmations, refunds, subscriptions
3. If the snippet doesn't contain enough info (missing amount, invoice number), use get_email_body to fetch the full content
4. Extract structured data: vendor_name, amount, currency, transaction_date, invoice_number, order_number, type
5. Set status='complete' if you have at least vendor + amount + date, otherwise 'partial'
6. Set confidence (0.0-1.0) based on how sure you are this is a real financial transaction
7. Mark non-transactional emails as 'ignored' (conversations, newsletters, notifications, account security, verification codes)
8. For partial transactions, check search_transactions to see if related data already exists

Rules:
- NEVER invent or hallucinate data. If you can't find an amount, leave it null and set status='partial'
- Amounts should be the exact number from the email, not estimated
- Currency should be detected from symbols (€=EUR, $=USD, £=GBP) or context
- Date should come from the email content, not the email send date (unless it's a receipt where they match)
- Process ALL emails presented to you — either save a transaction or mark as ignored
- You can save multiple transactions at once using save_transactions
- You can mark multiple emails as ignored at once using mark_emails_processed

Start by calling list_emails to see what needs processing."""


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
    try:
        account = SocialAccount.objects.get(user=email_obj.user, provider='google')
        token = SocialToken.objects.get(account=account)
    except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
        return "Error: no Google token available"

    resp = requests.get(
        f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{email_obj.message_id}',
        headers={'Authorization': f'Bearer {token.token}'},
        params={'format': 'full'},
    )
    if resp.status_code != 200:
        return f"Error fetching email: {resp.status_code}"

    data = resp.json()
    payload = data.get('payload', {})

    # Try to find text/plain part
    def find_text_part(payload):
        if payload.get('mimeType') == 'text/plain':
            body_data = payload.get('body', {}).get('data', '')
            if body_data:
                return base64.urlsafe_b64decode(body_data).decode('utf-8', errors='replace')
        for part in payload.get('parts', []):
            result = find_text_part(part)
            if result:
                return result
        return None

    text = find_text_part(payload)
    if text:
        # Limit to avoid sending too much to the LLM
        return text[:3000]
    return "No text content found in email."


def _fetch_microsoft_body(email_obj):
    """Fetch email body from Microsoft Graph API."""
    try:
        account = SocialAccount.objects.get(user=email_obj.user, provider='microsoft')
        token = SocialToken.objects.get(account=account)
    except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
        return "Error: no Microsoft token available"

    resp = requests.get(
        f'https://graph.microsoft.com/v1.0/me/messages/{email_obj.message_id}',
        headers={'Authorization': f'Bearer {token.token}'},
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

    return content[:3000]


def _execute_get_email_body(user, params):
    email_id = params.get('email_id')
    try:
        email_obj = Email.objects.get(id=email_id, user=user)
    except Email.DoesNotExist:
        return {"error": f"Email {email_id} not found"}

    if email_obj.provider == 'google':
        body = _fetch_gmail_body(email_obj)
    elif email_obj.provider == 'microsoft':
        body = _fetch_microsoft_body(email_obj)
    else:
        body = "Unknown provider"

    return {"email_id": email_id, "body": body}


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

        # Parse date safely
        tx_date = None
        if tx_data.get('transaction_date'):
            try:
                from datetime import date
                tx_date = date.fromisoformat(tx_data['transaction_date'])
            except ValueError:
                pass

        # Check for existing transaction on same email
        existing = None
        if email_obj:
            existing = Transaction.objects.filter(user=user, email=email_obj).first()

        if existing:
            # Update existing
            existing.type = tx_data.get('type', existing.type)
            existing.vendor_name = tx_data.get('vendor_name', existing.vendor_name)
            if amount is not None:
                existing.amount = amount
            existing.currency = tx_data.get('currency', existing.currency) or 'EUR'
            if tx_date:
                existing.transaction_date = tx_date
            existing.invoice_number = tx_data.get('invoice_number', existing.invoice_number) or ''
            existing.order_number = tx_data.get('order_number', existing.order_number) or ''
            existing.description = tx_data.get('description', existing.description) or ''
            existing.confidence = tx_data.get('confidence', existing.confidence)
            existing.status = tx_data.get('status', existing.status)
            existing.raw_data = tx_data
            existing.save()
            updated += 1
        else:
            Transaction.objects.create(
                user=user,
                email=email_obj,
                type=tx_data.get('type', 'other'),
                vendor_name=tx_data.get('vendor_name', 'Unknown'),
                amount=amount,
                currency=tx_data.get('currency', 'EUR') or 'EUR',
                transaction_date=tx_date,
                invoice_number=tx_data.get('invoice_number', '') or '',
                order_number=tx_data.get('order_number', '') or '',
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
    qs = Transaction.objects.filter(user=user)
    if params.get('vendor_name'):
        qs = qs.filter(vendor_name__icontains=params['vendor_name'])
    if params.get('order_number'):
        qs = qs.filter(order_number=params['order_number'])
    if params.get('invoice_number'):
        qs = qs.filter(invoice_number=params['invoice_number'])
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
            'status': t.status,
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


def classify_emails(user):
    """
    Run the Claude agent to classify emails and extract transactions.
    Returns stats dict.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        import os
        api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return {"error": "ANTHROPIC_API_KEY not configured"}

    # Check there are emails to process
    new_count = Email.objects.filter(user=user, status=Email.Status.NEW).count()
    partial_count = Transaction.objects.filter(user=user, status=Transaction.Status.PARTIAL).count()
    if new_count == 0 and partial_count == 0:
        return {"message": "No emails to process", "processed": 0}

    client = anthropic.Anthropic(api_key=api_key)
    messages = []

    stats = {
        "transactions_created": 0,
        "transactions_updated": 0,
        "emails_processed": 0,
        "emails_ignored": 0,
        "api_calls": 0,
    }

    # Start the agentic loop
    response = _call_api_with_retry(
        client,
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        tools=TOOLS,
        messages=[{"role": "user", "content": f"Process all unprocessed emails for this user. There are {new_count} new emails and {partial_count} partial transactions to review."}],
    )
    stats["api_calls"] += 1

    messages.append({"role": "user", "content": f"Process all unprocessed emails for this user. There are {new_count} new emails and {partial_count} partial transactions to review."})

    # Agentic loop — keep going while Claude wants to use tools
    max_iterations = 30  # Safety limit
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        # Check if Claude wants to use tools
        if response.stop_reason != "tool_use":
            break

        # Process all tool calls in the response
        tool_results = []
        assistant_content = response.content

        for block in assistant_content:
            if block.type == "tool_use":
                tool_name = block.name
                tool_input = block.input

                logger.info(f'Agent calling tool: {tool_name} with {json.dumps(tool_input)[:200]}')

                handler = TOOL_HANDLERS.get(tool_name)
                if handler:
                    try:
                        result = handler(user, tool_input)

                        # Track stats
                        if tool_name == 'save_transactions':
                            stats["transactions_created"] += result.get("created", 0)
                            stats["transactions_updated"] += result.get("updated", 0)
                        elif tool_name == 'mark_emails_processed':
                            if tool_input.get('status') == 'processed':
                                stats["emails_processed"] += result.get("marked", 0)
                            elif tool_input.get('status') == 'ignored':
                                stats["emails_ignored"] += result.get("marked", 0)

                    except Exception as e:
                        logger.error(f'Tool {tool_name} error: {e}')
                        result = {"error": str(e)}
                else:
                    result = {"error": f"Unknown tool: {tool_name}"}

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, default=str),
                })

        # Send tool results back to Claude
        messages.append({"role": "assistant", "content": assistant_content})
        messages.append({"role": "user", "content": tool_results})

        response = _call_api_with_retry(
            client,
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=messages,
        )
        stats["api_calls"] += 1

    # Extract any final text message
    final_message = ""
    for block in response.content:
        if hasattr(block, 'text'):
            final_message = block.text
            break

    stats["agent_summary"] = final_message
    return stats
