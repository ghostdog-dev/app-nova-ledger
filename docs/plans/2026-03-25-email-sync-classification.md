# Email Sync & LLM Classification — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fetch emails from Gmail/Microsoft, pre-filter out noise, then use a Claude AI agent to classify transactional emails and extract structured financial data.

**Architecture:** Two-phase pipeline. Phase 1: Email fetcher pulls emails from Gmail API / Microsoft Graph, applies provider-specific pre-filters (exclude spam/promos/social/forums for Gmail, exclude JunkEmail for Microsoft), stores raw metadata in DB with deduplication via provider message_id. Phase 2: Claude Agent (Haiku via Agent SDK) with tools to read emails, fetch bodies on demand, and save structured transactions. Small batches (10-20) processed in parallel with rate limiting and backoff.

**Tech Stack:** Django 6 / DRF, Gmail API, Microsoft Graph API, Claude Agent SDK (`claude-agent-sdk`), Anthropic API (Haiku), `requests` for API calls.

---

## File Structure

```
emails/                         # New Django app
  __init__.py
  models.py                     # Email + Transaction models
  admin.py                      # Admin registration
  services/
    __init__.py
    gmail_fetcher.py             # Gmail API fetch + pre-filter
    microsoft_fetcher.py         # Microsoft Graph fetch + pre-filter
    agent.py                     # Claude Agent — tools + orchestration
  serializers.py                 # DRF serializers for API responses
  urls.py                        # API endpoints
  views.py                       # Sync + classify views
```

---

### Task 1: Create `emails` Django app + models

**Files:**
- Create: `emails/__init__.py`, `emails/models.py`, `emails/admin.py`, `emails/migrations/`
- Modify: `nova_ledger/settings.py` (add to INSTALLED_APPS)

- [ ] **Step 1: Create app and models**

`emails/models.py`:
```python
from django.conf import settings
from django.db import models


class Email(models.Model):
    class Provider(models.TextChoices):
        GOOGLE = 'google'
        MICROSOFT = 'microsoft'

    class Status(models.TextChoices):
        NEW = 'new'
        PROCESSED = 'processed'
        IGNORED = 'ignored'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='emails')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    message_id = models.CharField(max_length=255)  # Provider's unique ID
    from_address = models.EmailField(max_length=255, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    snippet = models.TextField(blank=True)  # ~200 char preview
    date = models.DateTimeField()  # Email send date
    labels = models.JSONField(default=list)  # Gmail labels or MS categories
    has_attachments = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'provider', 'message_id')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'provider', 'message_id']),
        ]

    def __str__(self):
        return f'{self.from_address}: {self.subject[:50]}'


class Transaction(models.Model):
    class Type(models.TextChoices):
        INVOICE = 'invoice'
        RECEIPT = 'receipt'
        ORDER = 'order'
        PAYMENT = 'payment'
        SHIPPING = 'shipping'
        REFUND = 'refund'
        SUBSCRIPTION = 'subscription'
        OTHER = 'other'

    class Status(models.TextChoices):
        PARTIAL = 'partial'
        COMPLETE = 'complete'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    email = models.ForeignKey(Email, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PARTIAL)
    vendor_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='EUR')  # ISO 4217
    transaction_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    order_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict)  # All data extracted by AI
    confidence = models.FloatField(default=0.0)  # 0-1 AI confidence
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'type']),
        ]

    def __str__(self):
        return f'{self.vendor_name} — {self.amount} {self.currency}'
```

- [ ] **Step 2: Register admin + add to INSTALLED_APPS**

`emails/admin.py` — register both models.
Add `'emails'` to `INSTALLED_APPS` in `nova_ledger/settings.py`.

- [ ] **Step 3: Run migrations**

```bash
python manage.py makemigrations emails
python manage.py migrate
```

- [ ] **Step 4: Commit**

```bash
git add emails/ nova_ledger/settings.py
git commit -m "feat(emails): add Email and Transaction models"
```

---

### Task 2: Gmail Fetcher

**Files:**
- Create: `emails/services/__init__.py`, `emails/services/gmail_fetcher.py`

- [ ] **Step 1: Implement Gmail fetcher**

`emails/services/gmail_fetcher.py`:
- `fetch_emails(user) -> int` (returns count of new emails saved)
- Get Google SocialToken from allauth
- Query Gmail API: `GET /gmail/v1/users/me/messages` with `q=-category:promotions -category:social -category:forums -in:spam`
- Paginate through all results using `nextPageToken`
- For each message, fetch metadata (from, subject, date, snippet, labels)
- Skip if `message_id` already in DB (dedup)
- Bulk create Email objects
- Parse `From` header into `from_name` + `from_address`
- Detect `has_attachments` from payload parts

- [ ] **Step 2: Test manually via Django shell**

```bash
python manage.py shell -c "
from emails.services.gmail_fetcher import fetch_emails
from accounts.models import CustomUser
user = CustomUser.objects.get(pk=13)
count = fetch_emails(user)
print(f'Fetched {count} emails')
"
```

- [ ] **Step 3: Commit**

```bash
git add emails/services/
git commit -m "feat(emails): add Gmail fetcher with pre-filtering"
```

---

### Task 3: Microsoft Fetcher

**Files:**
- Create: `emails/services/microsoft_fetcher.py`

- [ ] **Step 1: Implement Microsoft fetcher**

`emails/services/microsoft_fetcher.py`:
- `fetch_emails(user) -> int`
- Get Microsoft SocialToken from allauth
- Query Microsoft Graph: `GET /v1.0/me/mailFolders/inbox/messages` (skips JunkEmail by targeting inbox)
- Also fetch from `SentItems` folder (useful for sent invoices)
- Paginate via `@odata.nextLink`
- Same dedup + bulk create logic as Gmail
- Map Microsoft fields to Email model (from → emailAddress, subject, bodyPreview → snippet, receivedDateTime → date)

- [ ] **Step 2: Test manually**

- [ ] **Step 3: Commit**

```bash
git add emails/services/microsoft_fetcher.py
git commit -m "feat(emails): add Microsoft Graph fetcher"
```

---

### Task 4: Sync API endpoint

**Files:**
- Create: `emails/urls.py`, `emails/views.py`, `emails/serializers.py`
- Modify: `nova_ledger/urls.py`

- [ ] **Step 1: Create serializers, views, URLs**

`emails/views.py`:
- `POST /api/emails/sync/` — triggers fetch for authenticated user (both providers if linked)
- Returns: `{ "google": N, "microsoft": M, "total_new": N+M }`

`emails/serializers.py`:
- `EmailSerializer` — read-only serializer for Email model
- `TransactionSerializer` — read-only serializer for Transaction model

`emails/urls.py`:
- Wire up sync endpoint

- [ ] **Step 2: Add to main urls.py**

```python
path('api/emails/', include('emails.urls')),
```

- [ ] **Step 3: Test via curl/httpie**

```bash
curl -X POST http://localhost:8000/api/emails/sync/ -H "Cookie: access_token=<jwt>"
```

- [ ] **Step 4: Commit**

```bash
git add emails/views.py emails/urls.py emails/serializers.py nova_ledger/urls.py
git commit -m "feat(emails): add sync API endpoint"
```

---

### Task 5: Claude Agent with tools

**Files:**
- Create: `emails/services/agent.py`
- Modify: `requirements.txt` (add `anthropic`)
- Modify: `.env` (add `ANTHROPIC_API_KEY`)

- [ ] **Step 1: Add anthropic to requirements + .env**

```bash
pip install anthropic
```

Add `anthropic` to `requirements.txt`.
Add `ANTHROPIC_API_KEY` to `.env.example`.

- [ ] **Step 2: Implement agent with tools**

`emails/services/agent.py`:
- `classify_emails(user) -> dict` — main entry point
- Queries Email objects with `status=new` for the user
- Also queries Transaction objects with `status=partial`
- Processes in batches of 10-20 emails
- For each batch, creates Claude agent (Haiku) with tools:

**Tools defined:**
1. `list_emails` — list emails from DB (filter by status, date range, provider)
2. `get_email_body` — fetch full body from Gmail/Microsoft API for a specific email
3. `save_transactions` — save multiple Transaction objects at once (structured output with type, vendor, amount, currency, date, invoice_number, order_number, description, confidence, status)
4. `search_transactions` — search existing transactions (for correlation)
5. `mark_emails_processed` — mark emails as processed or ignored

**System prompt for agent:**
- You are a financial email classifier
- Analyze email metadata (from, subject, snippet, date)
- Identify transactional emails: invoices, receipts, orders, payments, shipping, refunds, subscriptions
- If you need more details (amount, invoice number), use get_email_body
- Extract: vendor_name, amount, currency, transaction_date, invoice_number, order_number, type
- Set status=complete if all key fields found, status=partial if missing amount or other key data
- Set confidence 0-1
- Ignore non-transactional emails (conversations, newsletters, notifications)
- For partial transactions, check if new emails complete the data

**Rate limiting:**
- Max 3 parallel batch calls
- Retry with exponential backoff on 429/529 errors
- Track token usage

- [ ] **Step 3: Test via Django shell**

```bash
python manage.py shell -c "
from emails.services.agent import classify_emails
from accounts.models import CustomUser
user = CustomUser.objects.get(pk=13)
result = classify_emails(user)
print(result)
"
```

- [ ] **Step 4: Commit**

```bash
git add emails/services/agent.py requirements.txt .env.example
git commit -m "feat(emails): add Claude agent for email classification"
```

---

### Task 6: Classify API endpoint + test page

**Files:**
- Modify: `emails/views.py`, `emails/urls.py`

- [ ] **Step 1: Add classify endpoint**

`POST /api/emails/classify/` — triggers agent classification for authenticated user
Returns: `{ "processed": N, "transactions_created": M, "transactions_updated": K }`

- [ ] **Step 2: Add list endpoints**

`GET /api/emails/` — list fetched emails (with filters: status, provider, date)
`GET /api/emails/transactions/` — list extracted transactions (with filters: type, status, date, vendor)

- [ ] **Step 3: Simple test HTML page** (like login page)

`GET /emails/test/` — simple page with buttons:
- "Sync Emails" → calls sync endpoint, shows results
- "Classify" → calls classify endpoint, shows results
- Table showing transactions extracted

- [ ] **Step 4: Commit**

```bash
git add emails/
git commit -m "feat(emails): add classify endpoint and test page"
```
