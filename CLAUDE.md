# Nova Ledger

## Project Overview
Backend Django API for automated accounting. Fetches emails from user mailboxes (Gmail, Microsoft), classifies transactional emails with AI, extracts structured financial data, and correlates transactions.

Target: PME/startups. Replace manual bookkeeping with AI-driven transaction extraction.

## Tech Stack
- Python 3.13 / Django 6.0 / DRF
- django-allauth (Google + Microsoft OAuth)
- dj-rest-auth + simplejwt (JWT auth)
- Anthropic API (Claude Haiku 4.5) for AI classification
- python-dotenv

## Project Structure
```
nova-ledger/
  manage.py
  requirements.txt
  .env / .env.example
  nova_ledger/          # Django project config
    settings.py
    urls.py
  accounts/             # Auth app (email-based, OAuth Google+Microsoft)
    models.py           # CustomUser (email as identifier)
    serializers.py      # OAuth + register serializers
    views.py            # Login/callback pages (dev)
  emails/               # Email sync + AI classification app
    models.py           # Email, Transaction models
    services/
      pipeline.py       # Multi-pass AI pipeline (MAIN ENTRY POINT)
      agent.py          # Tool handlers, RateLimiter, vendor normalization
      gmail_fetcher.py  # Gmail API fetch + pre-filter
      microsoft_fetcher.py  # Microsoft Graph fetch
      token_refresh.py  # Auto-refresh OAuth tokens
      prefilter.py      # Rule-based prefilter (deprecated — AI handles triage)
      merge.py          # Post-processing merge (safety net)
    views.py            # API endpoints + test page HTML
    urls.py
    serializers.py
  docs/                 # Specs and plans
```

## AI Pipeline Architecture
The core of the app. 4-pass pipeline, each pass is a specialized AI task.

```
POST /api/emails/classify/ → run_pipeline(user)

Pass 1 — TRIAGE (fast, batches of 40, JSON response, no tool_use)
  "Is this email transactional?" → yes/no for each email
  Parallel: 3 concurrent batches

Pass 2 — EXTRACTION (batches of 15, tool_use with body fetch)
  "Extract all financial data from this email"
  Tools: get_email_body, save_transactions, mark_emails_processed
  Parallel: 2 concurrent batches

Pass 3 — CORRELATION (per vendor group, JSON response)
  "Should these transactions from the same vendor be merged?"

Pass 4 — VERIFICATION (all transactions at once, JSON response)
  "Review for duplicates, false positives, missing data"
```

### Agent Design Principles (Anthropic best practices)
- **One task per pass** — each pass does ONE thing well. Don't mix triage + extraction.
- **Gather → Act → Verify → Repeat** — the core agentic loop
- **Small batches** — avoid hallucination from too much data at once
- **Structured output** — use `strict: true` on tool schemas for guaranteed conformance
- **Context isolation** — fresh context per batch, pass existing transactions as context
- **The AI decides, code provides tools** — never hardcode business logic that the AI should handle
- **Failed payments are real events** — keep them, mark with "FAILED" in description
- **AI computes derivable data** — HT from TTC-TVA, but NEVER invents numbers

## Data Models

### Email
- provider (google/microsoft), message_id (dedup), from_address, from_name
- subject, snippet, date, labels, has_attachments, has_list_unsubscribe
- status: new → triage_passed → processed/ignored

### Transaction
- Core: vendor_name, amount (TTC), currency, transaction_date, type, status (complete/partial)
- Accounting: amount_tax_excl (HT), tax_amount (TVA), tax_rate, payment_method, payment_reference
- References: invoice_number, order_number, items (JSON array of {name, qty, unit_price})
- Meta: description, raw_data (JSON), confidence (0-1), email FK

## API Endpoints
- `POST /api/emails/sync/` — fetch emails from Gmail/Microsoft (default: 30 days)
- `POST /api/emails/classify/` — run full AI pipeline
- `GET /api/emails/` — list emails (filter: provider, status)
- `GET /api/emails/transactions/` — list transactions (filter: type, status, vendor)
- `POST /api/emails/merge/` — manual merge trigger
- `/emails/test/` — dev test page with dashboard
- `/login/` + `/callback/` — OAuth dev login flow

## Key Design Decisions
- Email is the PRIMARY data source (most universal). Providers (Stripe, Qonto, etc.) will be added later for enrichment.
- OAuth tokens auto-refresh via token_refresh.py (60s buffer before expiry)
- Rate limiting: RateLimiter class tracks tokens/minute, conservative 40k/min limit (API limit is 50k)
- Parallel processing: ThreadPoolExecutor with staggered launches
- Dedup: message_id for emails, multi-criteria for transactions (order_number, invoice_number, vendor+amount+date)
- _normalize_vendor_name strips corporate suffixes (PBC, Inc, Ltd, SAS) + commas

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in secrets + ANTHROPIC_API_KEY
python manage.py migrate
python manage.py createsuperuser
# Create SocialApp entries via admin for Google and Microsoft
python manage.py runserver
# Go to /login/ → OAuth → /emails/test/ → Sync → Classify
```

## Important Notes
- ANTHROPIC_API_KEY required in .env for classification
- SocialApp entries must exist in DB for OAuth
- EMAIL_BACKEND is console in dev
- Secrets in .env, never committed
- Dev test pages (/login/, /emails/test/) are not production — just for testing the pipeline
