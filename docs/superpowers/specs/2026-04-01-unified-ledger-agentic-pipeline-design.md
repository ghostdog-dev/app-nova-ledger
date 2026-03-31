# Unified Ledger & Agentic Pipeline — Design Spec

## Problem

Nova Ledger connects to multiple financial services (Stripe, Mollie, PayPal, bank APIs, email) but the current correlation system uses email as the only hub. If no email exists for a transaction, no correlation happens. The agentic loop is a naive `while` with no recovery paths, no state management, and no streaming. The frontend displays wrong status values and missing fields. Result: data quality is poor, correlations are incomplete, reports are useless.

## Solution

Replace the entire pipeline with a **Unified Ledger** architecture where every data source is a first-class citizen, and a **team of specialized AI agents** (each with a verifier and cleaner) handles ingestion, enrichment, correlation, computation, and verification. Add bank file import (CSV/OFX) for users without bank API access.

---

## Architecture

### Data Model

**UnifiedTransaction** — Every source (Stripe charge, Mollie payment, bank debit, email invoice, CSV import) is normalized into this single model. Fields:

- Identity: `id`, `public_id` (UUID), `user` (FK)
- Source: `source_type` (stripe|mollie|paypal|bank_api|bank_import|email|...), `source_id`, `source_content_type` + `source_object_id` (GenericFK to original model)
- Normalized data: `direction` (inflow|outflow), `category` (revenue|expense_service|expense_goods|expense_shipping|purchase_cost|tax|fee|refund|transfer|salary|other), `amount`, `currency`, `amount_tax_excl`, `tax_amount`, `tax_rate`, `transaction_date`
- Identification: `vendor_name`, `vendor_name_normalized` (computed on save), `description`, `reference` (invoice/order/payment ref), `payment_method`, `items` (JSONField)
- Quality: `confidence` (0.0-1.0), `completeness` (complete|partial|minimal)
- Evidence: `evidence_role` (primary|confirmation|enrichment|contradiction), `related_emails` (M2M to Email)
- Correlation: `cluster` (FK to TransactionCluster, nullable)
- Accounting: `pcg_code`, `pcg_label`, `business_personal` (business|personal|unknown), `tva_deductible` (bool)
- Timestamps: `created_at`, `updated_at`

**TransactionCluster** — Groups related UnifiedTransactions into a single business operation:

- Identity: `id`, `public_id` (UUID), `user` (FK)
- Summary: `label` (AI-generated), `cluster_type` (sale|purchase|subscription|refund|transfer|salary|tax_payment|other)
- Computed metrics: `total_revenue`, `total_cost`, `margin`, `total_tax_collected`, `total_tax_deductible`
- Quality: `confidence`, `is_complete` (bool), `corroboration_score` (float), `verification_status` (auto|verified|disputed)
- Audit: `match_reasoning` (TextField), `evidence_summary` (JSONField), `created_by` (ai_agent|manual|import)

**BankFileImport** — Tracks uploaded bank statement files:

- `user` (FK), `file` (FileField), `file_type` (csv|ofx|qif|camt053)
- `bank_name`, `account_identifier` (IBAN or account number)
- `status` (pending|parsing|parsed|failed), `rows_total`, `rows_imported`, `rows_skipped`
- `parser_used`, `column_mapping` (JSONField), `error_message`
- `date_from`, `date_to`, `uploaded_at`

### Agent Team Architecture

Each pipeline phase has a **specialized agent** with:
- **Worker** — does the main LLM work
- **Verifier** — independent LLM reviewing worker output (fresh context)
- **Cleaner** — post-processing cleanup (dedup, normalization, validation)

Model selection per role:
- `claude-haiku-4-5-20251001` — Triage, simple classification, tax computation verification, cleanup tasks
- `claude-sonnet-4-5-20250929` — Extraction, correlation, enrichment (complex reasoning)
- Verifiers use Haiku when checking simple decisions, Sonnet when auditing complex correlations

### Pipeline Phases

**Phase 1: INGESTION** (no LLM) — Run normalizers per provider, create UnifiedTransactions. Parallel by provider.

**Phase 2: ENRICHMENT** (LLM agent) — Classify expenses (PCG codes), detect vendor types, compute tax fields. Worker uses Sonnet, Verifier uses Haiku.

**Phase 3: CORRELATION** (LLM agent — the core) — Group UnifiedTransactions into TransactionClusters. Any source can match any other source. Worker uses Sonnet, Verifier uses Sonnet (complex reasoning needed).

**Phase 4: COMPUTATION** (no LLM) — Calculate cluster metrics: revenue, costs, margin, tax totals. Pure Python.

**Phase 5: VERIFICATION** (LLM agent) — Audit clusters with confidence < 0.8, review contradictions. Worker uses Haiku for simple checks, Sonnet for complex anomalies.

### Agentic Loop (inspired by Claude Code report)

State machine with immutable state rebuilt at each transition. Recovery paths:
1. Rate Limit — max 3 retries with exponential backoff
2. Token Overflow — compact context once, then skip phase
3. Max Output Tokens — resume message, max 20 turns per phase
4. Tool Error (write operations) — max 3 retries per phase
5. Circuit Breaker OPEN — 60s recovery timeout
6. Phase Timeout — 10 min per phase, save progress and continue

Each agent must produce an action plan before executing (tool: `think`).

### Bank File Import

Parsers: CSV (with known bank signatures + heuristic mapping + LLM fallback), OFX, CAMT.053. Deduplication against existing data. Preview + confirm flow for uncertain mappings.

### Email Dual Role

Emails can be:
- **Primary source** — only source of truth (no matching API data)
- **Confirmation** — confirms existing data from another source
- **Enrichment** — adds missing fields (items, tax, attachments)
- **Contradiction** — conflicts with existing data, flagged for review

The email agent checks existing UnifiedTransactions BEFORE deciding the role.

### Frontend

- Fix status enum: backend returns `matched|pending|orphan` based on cluster membership
- New types: UnifiedTransaction, TransactionCluster (replace InvoiceMini/PaymentMini)
- TransactionsPage: filterable by source, status, category, direction. Toggle list/cluster view
- ClusterDetailModal: timeline, financial summary, evidence, actions
- DashboardPage: KPIs (revenue, costs, margin, reconciliation rate), monthly chart, per-source breakdown, alerts
- BankImportPage: upload, preview mapping, confirm, import history
- ExecutionDetailPage: show 5 pipeline phases with progress

### What Gets Replaced

- `ai_agent/services/agent.py` (naive while loop) → `ai_agent/services/orchestrator.py` + `ai_agent/services/tools.py`
- `ai_agent/services/correlation.py` (email-only) → Phase CORRELATION in orchestrator
- `banking/services/correlation.py` (bank↔email deterministic) → merged into Phase CORRELATION
- 3x `normalize_vendor()` implementations → 1x unified in `ai_agent/services/normalization.py`
- `TransactionMatch` + `ProviderMatch` → `TransactionCluster`
- `emails.Transaction` as hub → `UnifiedTransaction` (all sources equal)
- Old frontend types (InvoiceMini, PaymentMini) → new unified types
