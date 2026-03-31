# Unified Ledger & Agentic Pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the email-centric correlation system with a Unified Ledger where every data source is a first-class citizen, powered by a team of specialized AI agents with verifiers, cleaners, and recovery paths.

**Architecture:** Each financial source (Stripe, Mollie, PayPal, bank API, bank CSV import, email) is normalized into a `UnifiedTransaction` model. A team of specialized LLM agents (each with worker/verifier/cleaner) groups transactions into `TransactionCluster` objects representing complete business operations. The pipeline is a state machine with 6 named recovery paths.

**Tech Stack:** Django 5, Python 3.12, Anthropic SDK (claude-haiku-4-5-20251001 for simple tasks, claude-sonnet-4-5-20250929 for complex reasoning), React 19, TypeScript, Vite 7, Zustand, Django Channels (WebSocket)

---

## File Structure

### New files to create

```
ai_agent/
├── services/
│   ├── orchestrator.py          # State machine, recovery paths, agent dispatcher
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseAgent class (worker/verifier/cleaner pattern)
│   │   ├── ingestion.py         # IngestionAgent — no LLM, runs normalizers
│   │   ├── enrichment.py        # EnrichmentAgent — PCG codes, vendor types, tax
│   │   ├── correlation.py       # CorrelationAgent — cluster creation (the core)
│   │   ├── computation.py       # ComputationAgent — pure Python metrics
│   │   └── verification.py      # VerificationAgent — audit clusters
│   ├── normalizers/
│   │   ├── __init__.py
│   │   ├── base.py              # BaseNormalizer interface
│   │   ├── stripe.py            # StripeCharge/Payout → UnifiedTransaction
│   │   ├── mollie.py            # MolliePayment → UnifiedTransaction
│   │   ├── paypal.py            # PayPalTransaction → UnifiedTransaction
│   │   ├── bank_api.py          # BankTransaction (Powens) → UnifiedTransaction
│   │   ├── bank_import.py       # CSV/OFX parsed rows → UnifiedTransaction
│   │   └── email.py             # emails.Transaction → UnifiedTransaction
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── csv_parser.py        # CSV bank statement parser (multi-bank)
│   │   ├── ofx_parser.py        # OFX/QFX parser
│   │   └── camt053_parser.py    # CAMT.053 SEPA parser
│   ├── normalization.py         # Single unified vendor normalization
│   └── tools.py                 # LLM tool definitions + handlers
├── models.py                    # Add UnifiedTransaction, TransactionCluster, BankFileImport

ai_agent/tests/
├── __init__.py
├── test_normalization.py
├── test_normalizers.py
├── test_parsers.py
├── test_orchestrator.py
├── test_agents.py
└── test_tools.py

core/
├── views/
│   ├── unified_transactions.py  # New API views
│   ├── clusters.py              # New API views
│   └── bank_import.py           # Upload + confirm views
├── serializers.py               # Add new serializers

frontend-vite/src/
├── types/unified.ts             # New TypeScript types
├── pages/
│   ├── TransactionsPage.tsx     # Refactored
│   ├── DashboardPage.tsx        # Enriched
│   └── BankImportPage.tsx       # New
├── components/
│   ├── clusters/
│   │   ├── cluster-detail-modal.tsx
│   │   └── cluster-card.tsx
│   └── bank-import/
│       ├── upload-zone.tsx
│       └── mapping-preview.tsx
├── hooks/
│   ├── use-unified-transactions.ts
│   ├── use-clusters.ts
│   └── use-bank-import.ts
```

### Existing files to modify

```
ai_agent/models.py               # Add 3 new models
ai_agent/urls.py                 # Add new endpoints
ai_agent/views.py                # Add new views
nova_ledger/settings.py          # Add new AI settings
core/urls.py                     # Add new routes
core/serializers.py              # Add new serializers
frontend-vite/src/types/index.ts # Add new types
```

---

## Task 1: Unified Vendor Normalization

**Files:**
- Create: `ai_agent/services/normalization.py`
- Create: `ai_agent/tests/__init__.py`
- Create: `ai_agent/tests/test_normalization.py`

This replaces the 3 different `normalize_vendor()` implementations currently scattered across the codebase.

- [ ] **Step 1: Write failing tests for vendor normalization**

```python
# ai_agent/tests/test_normalization.py
from django.test import TestCase
from ai_agent.services.normalization import normalize_vendor


class NormalizeVendorTest(TestCase):
    """Test the unified vendor normalization pipeline."""

    def test_strip_bank_prefixes(self):
        self.assertEqual(normalize_vendor('CB*AMAZON PARIS'), 'amazon')
        self.assertEqual(normalize_vendor('PRLV NETFLIX'), 'netflix')
        self.assertEqual(normalize_vendor('VIR STRIPE'), 'stripe')
        self.assertEqual(normalize_vendor('CARTE UBER'), 'uber')

    def test_strip_corporate_suffixes(self):
        self.assertEqual(normalize_vendor('Amazon Inc.'), 'amazon')
        self.assertEqual(normalize_vendor('OVH SAS'), 'ovh')
        self.assertEqual(normalize_vendor('Stripe Ltd'), 'stripe')
        self.assertEqual(normalize_vendor('Google LLC'), 'google')
        self.assertEqual(normalize_vendor('SAP GMBH'), 'sap')
        self.assertEqual(normalize_vendor('Apple Corp.'), 'apple')

    def test_strip_city_and_trailing_numbers(self):
        self.assertEqual(normalize_vendor('AMAZON PARIS 02'), 'amazon')
        self.assertEqual(normalize_vendor('UBER EATS LYON 69003'), 'uber eats')
        self.assertEqual(normalize_vendor('CARREFOUR MARKET NANTES'), 'carrefour market')

    def test_collapse_whitespace(self):
        self.assertEqual(normalize_vendor('  UBER   EATS  '), 'uber eats')

    def test_empty_and_none(self):
        self.assertEqual(normalize_vendor(''), '')
        self.assertEqual(normalize_vendor(None), '')

    def test_already_clean(self):
        self.assertEqual(normalize_vendor('netflix'), 'netflix')
        self.assertEqual(normalize_vendor('Spotify'), 'spotify')

    def test_fuzzy_match(self):
        from ai_agent.services.normalization import vendors_match
        self.assertTrue(vendors_match('amazon', 'amazon prime'))
        self.assertTrue(vendors_match('uber eats', 'uber'))
        self.assertFalse(vendors_match('netflix', 'spotify'))
        self.assertTrue(vendors_match('google cloud', 'google'))

    def test_real_world_bank_labels(self):
        self.assertEqual(normalize_vendor('CB AMAZON.FR MARKETPLACE'), 'amazon.fr marketplace')
        self.assertEqual(normalize_vendor('PRLV SEPA OVH SAS'), 'ovh')
        self.assertEqual(normalize_vendor('VIR INST MOLLIE'), 'mollie')
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test ai_agent.tests.test_normalization -v 2`
Expected: ImportError — `ai_agent.services.normalization` does not exist

- [ ] **Step 3: Implement normalize_vendor and vendors_match**

```python
# ai_agent/services/normalization.py
"""
Unified vendor name normalization — single source of truth.

Replaces:
- banking.services.utils.normalize_vendor()
- ai_agent.services.agent._normalize_vendor_name()
- emails.services.merge._normalize_vendor()
"""
import re

# Bank transaction prefixes (FR banking conventions)
_BANK_PREFIXES = re.compile(
    r'^(CB\*?|CARTE\s+|PRLV\s+(SEPA\s+)?|VIR\s+(INST\s+|SEPA\s+)?|'
    r'CHQ\s+|RET\s+DAB\s+|ECH\s+|COTIS\s+)',
    re.IGNORECASE,
)

# Corporate suffixes
_CORPORATE_SUFFIXES = re.compile(
    r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sarl\.?|sa\.?|gmbh\.?|'
    r'co\.?|corp\.?|limited|pty\.?|plc\.?|ag\.?|bv\.?|nv\.?)\s*$',
    re.IGNORECASE,
)

# French city names commonly appended by banks
_FRENCH_CITIES = re.compile(
    r'\b(paris|lyon|marseille|toulouse|nice|nantes|strasbourg|montpellier|'
    r'bordeaux|lille|rennes|reims|toulon|grenoble|dijon|angers|'
    r'villeurbanne|roubaix|tourcoing)\b',
    re.IGNORECASE,
)

# Trailing numbers (postal codes, branch codes)
_TRAILING_NUMBERS = re.compile(r'\s+\d{2,5}\s*$')

# Multiple whitespace
_MULTI_SPACE = re.compile(r'\s+')


def normalize_vendor(name: str | None) -> str:
    """
    Normalize a vendor name for matching across sources.

    Pipeline:
    1. Strip bank prefixes (CB*, PRLV, VIR, CARTE, etc.)
    2. Strip corporate suffixes (Inc, Ltd, SAS, GMBH, etc.)
    3. Strip French city names
    4. Strip trailing numbers (postal codes)
    5. Lowercase, collapse whitespace, strip
    """
    if not name:
        return ''

    result = name.strip()

    # 1. Strip bank prefixes
    result = _BANK_PREFIXES.sub('', result)

    # 2. Lowercase
    result = result.lower()

    # 3. Strip corporate suffixes (may need multiple passes)
    for _ in range(2):
        result = _CORPORATE_SUFFIXES.sub('', result).strip(' ,.')

    # 4. Strip French cities
    result = _FRENCH_CITIES.sub('', result)

    # 5. Strip trailing numbers
    result = _TRAILING_NUMBERS.sub('', result)

    # 6. Collapse whitespace
    result = _MULTI_SPACE.sub(' ', result).strip()

    return result


def vendors_match(name_a: str, name_b: str) -> bool:
    """
    Check if two normalized vendor names refer to the same entity.

    Uses substring containment and Jaccard token overlap (>= 50%).
    Both inputs should already be normalized via normalize_vendor().
    """
    if not name_a or not name_b:
        return False

    a = normalize_vendor(name_a)
    b = normalize_vendor(name_b)

    if not a or not b:
        return False

    # Exact match
    if a == b:
        return True

    # Substring containment
    if a in b or b in a:
        return True

    # Jaccard token overlap >= 50%
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return False

    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)

    return jaccard >= 0.5
```

- [ ] **Step 4: Create `ai_agent/tests/__init__.py`**

```python
# ai_agent/tests/__init__.py
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test ai_agent.tests.test_normalization -v 2`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add ai_agent/services/normalization.py ai_agent/tests/__init__.py ai_agent/tests/test_normalization.py
git commit -m "feat: add unified vendor normalization (replaces 3 implementations)"
```

---

## Task 2: Data Models — UnifiedTransaction, TransactionCluster, BankFileImport

**Files:**
- Modify: `ai_agent/models.py`
- Create: `ai_agent/tests/test_models.py`

- [ ] **Step 1: Write failing tests for the new models**

```python
# ai_agent/tests/test_models.py
from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_agent.models import UnifiedTransaction, TransactionCluster, BankFileImport

User = get_user_model()


class UnifiedTransactionModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123'
        )

    def test_create_minimal(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='stripe',
            source_id='ch_abc123',
            direction='inflow',
            category='revenue',
            amount=Decimal('50.00'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='Acme Corp',
        )
        self.assertEqual(ut.vendor_name_normalized, 'acme')
        self.assertEqual(ut.direction, 'inflow')
        self.assertIsNotNone(ut.public_id)

    def test_vendor_name_normalized_auto(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='bank_api',
            source_id='tx_123',
            direction='outflow',
            category='expense_service',
            amount=Decimal('29.99'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='CB*NETFLIX INC PARIS 02',
        )
        self.assertEqual(ut.vendor_name_normalized, 'netflix')

    def test_completeness_complete(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='email',
            source_id='email_42',
            direction='outflow',
            category='expense_goods',
            amount=Decimal('100.00'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='Amazon',
        )
        self.assertEqual(ut.completeness, 'complete')

    def test_completeness_partial_no_amount(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='email',
            source_id='email_43',
            direction='outflow',
            category='expense_shipping',
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='UPS',
        )
        self.assertEqual(ut.completeness, 'partial')

    def test_unique_source(self):
        """Same source_type + source_id + user should not create duplicates."""
        UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_dup',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Test',
        )
        with self.assertRaises(Exception):
            UnifiedTransaction.objects.create(
                user=self.user, source_type='stripe', source_id='ch_dup',
                direction='inflow', category='revenue',
                amount=Decimal('50.00'), currency='EUR',
                transaction_date=date(2026, 3, 15), vendor_name='Test',
            )


class TransactionClusterModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test2@example.com', password='testpass123'
        )

    def test_create_cluster_with_transactions(self):
        cluster = TransactionCluster.objects.create(
            user=self.user,
            label='Vente produit X',
            cluster_type='sale',
        )
        ut1 = UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_1',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Client A',
            cluster=cluster,
        )
        ut2 = UnifiedTransaction.objects.create(
            user=self.user, source_type='bank_api', source_id='bt_1',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 17), vendor_name='STRIPE PAYOUT',
            cluster=cluster,
        )
        self.assertEqual(cluster.transactions.count(), 2)

    def test_recalculate_metrics(self):
        cluster = TransactionCluster.objects.create(
            user=self.user, label='Test', cluster_type='sale',
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_m1',
            direction='inflow', category='revenue',
            amount=Decimal('100.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Client',
            cluster=cluster,
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='email', source_id='em_m1',
            direction='outflow', category='purchase_cost',
            amount=Decimal('40.00'), currency='EUR',
            transaction_date=date(2026, 3, 10), vendor_name='Fournisseur',
            cluster=cluster,
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='email', source_id='em_m2',
            direction='outflow', category='expense_shipping',
            amount=Decimal('8.50'), currency='EUR',
            transaction_date=date(2026, 3, 12), vendor_name='UPS',
            cluster=cluster,
        )
        cluster.recalculate_metrics()
        self.assertEqual(cluster.total_revenue, Decimal('100.00'))
        self.assertEqual(cluster.total_cost, Decimal('48.50'))
        self.assertEqual(cluster.margin, Decimal('51.50'))


class BankFileImportModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test3@example.com', password='testpass123'
        )

    def test_create_import(self):
        imp = BankFileImport.objects.create(
            user=self.user,
            file_type='csv',
            bank_name='BNP Paribas',
            account_identifier='FR76 1234 5678 9012 3456 7890 123',
            status='pending',
        )
        self.assertEqual(imp.status, 'pending')
        self.assertEqual(imp.rows_imported, 0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test ai_agent.tests.test_models -v 2`
Expected: ImportError — models not defined yet

- [ ] **Step 3: Implement the 3 new models**

```python
# ai_agent/models.py — ADD these models after existing PipelineRun model
import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from ai_agent.services.normalization import normalize_vendor


class TransactionCluster(models.Model):
    class ClusterType(models.TextChoices):
        SALE = 'sale'
        PURCHASE = 'purchase'
        SUBSCRIPTION = 'subscription'
        REFUND = 'refund'
        TRANSFER = 'transfer'
        SALARY = 'salary'
        TAX_PAYMENT = 'tax_payment'
        OTHER = 'other'

    class VerificationStatus(models.TextChoices):
        AUTO = 'auto'
        VERIFIED = 'verified'
        DISPUTED = 'disputed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='transaction_clusters')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    label = models.CharField(max_length=255, default='')
    cluster_type = models.CharField(max_length=20, choices=ClusterType.choices,
                                    default=ClusterType.OTHER)

    # Computed metrics
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    margin = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_tax_collected = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    total_tax_deductible = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))

    # Quality
    confidence = models.FloatField(default=0.0)
    is_complete = models.BooleanField(default=False)
    corroboration_score = models.FloatField(default=0.0)
    verification_status = models.CharField(max_length=10, choices=VerificationStatus.choices,
                                           default=VerificationStatus.AUTO)

    # Audit
    match_reasoning = models.TextField(blank=True, default='')
    evidence_summary = models.JSONField(default=dict)
    created_by = models.CharField(max_length=20, default='ai_agent')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'cluster_type']),
            models.Index(fields=['user', 'verification_status']),
        ]

    def __str__(self):
        return f'Cluster #{self.pk} "{self.label}" ({self.cluster_type})'

    def recalculate_metrics(self):
        """Recompute all derived financial metrics from transactions."""
        txs = self.transactions.all()

        revenue = Decimal('0')
        cost = Decimal('0')
        tax_collected = Decimal('0')
        tax_deductible = Decimal('0')

        for tx in txs:
            amt = tx.amount or Decimal('0')
            tax = tx.tax_amount or Decimal('0')

            if tx.direction == 'inflow':
                revenue += amt
                tax_collected += tax
            else:
                cost += amt
                if tx.tva_deductible and tax:
                    tax_deductible += tax

        self.total_revenue = revenue
        self.total_cost = cost
        self.margin = revenue - cost
        self.total_tax_collected = tax_collected
        self.total_tax_deductible = tax_deductible

        # Corroboration: how many distinct sources confirm this cluster
        source_count = txs.values('source_type').distinct().count()
        if source_count >= 3:
            self.corroboration_score = 0.95
        elif source_count == 2:
            self.corroboration_score = 0.80
        else:
            self.corroboration_score = 0.50

        # Completeness: a sale is complete if it has revenue + (bank or provider)
        source_types = set(txs.values_list('source_type', flat=True))
        has_financial = bool(source_types & {'stripe', 'mollie', 'paypal', 'bank_api', 'bank_import'})
        has_document = bool(source_types & {'email'})
        self.is_complete = has_financial and (has_document or source_count >= 2)

        self.save()


class UnifiedTransaction(models.Model):
    class SourceType(models.TextChoices):
        STRIPE = 'stripe'
        MOLLIE = 'mollie'
        PAYPAL = 'paypal'
        BANK_API = 'bank_api'
        BANK_IMPORT = 'bank_import'
        EMAIL = 'email'
        GOCARDLESS = 'gocardless'
        QONTO = 'qonto'
        SHOPIFY = 'shopify'
        WOOCOMMERCE = 'woocommerce'
        PRESTASHOP = 'prestashop'
        MANUAL = 'manual'

    class Direction(models.TextChoices):
        INFLOW = 'inflow'
        OUTFLOW = 'outflow'

    class Category(models.TextChoices):
        REVENUE = 'revenue'
        EXPENSE_SERVICE = 'expense_service'
        EXPENSE_GOODS = 'expense_goods'
        EXPENSE_SHIPPING = 'expense_shipping'
        PURCHASE_COST = 'purchase_cost'
        TAX = 'tax'
        FEE = 'fee'
        REFUND = 'refund'
        TRANSFER = 'transfer'
        SALARY = 'salary'
        OTHER = 'other'

    class EvidenceRole(models.TextChoices):
        PRIMARY = 'primary'
        CONFIRMATION = 'confirmation'
        ENRICHMENT = 'enrichment'
        CONTRADICTION = 'contradiction'

    class Completeness(models.TextChoices):
        COMPLETE = 'complete'
        PARTIAL = 'partial'
        MINIMAL = 'minimal'

    # Identity
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='unified_transactions')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    # Source
    source_type = models.CharField(max_length=20, choices=SourceType.choices)
    source_id = models.CharField(max_length=255)
    source_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL,
                                            null=True, blank=True)
    source_object_id = models.PositiveIntegerField(null=True, blank=True)
    source_object = GenericForeignKey('source_content_type', 'source_object_id')

    # Normalized data
    direction = models.CharField(max_length=10, choices=Direction.choices)
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.OTHER)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='EUR')
    amount_tax_excl = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    transaction_date = models.DateField(null=True, blank=True)

    # Identification
    vendor_name = models.CharField(max_length=255, default='')
    vendor_name_normalized = models.CharField(max_length=255, default='', db_index=True)
    description = models.TextField(blank=True, default='')
    reference = models.CharField(max_length=255, blank=True, default='')
    payment_method = models.CharField(max_length=100, blank=True, default='')
    items = models.JSONField(default=list, blank=True)

    # Quality
    confidence = models.FloatField(default=0.5)
    completeness = models.CharField(max_length=10, choices=Completeness.choices,
                                    default=Completeness.PARTIAL)

    # Evidence
    evidence_role = models.CharField(max_length=15, choices=EvidenceRole.choices,
                                     default=EvidenceRole.PRIMARY)
    related_emails = models.ManyToManyField('emails.Email', blank=True,
                                            related_name='unified_transactions')

    # Correlation
    cluster = models.ForeignKey(TransactionCluster, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name='transactions')

    # Accounting
    pcg_code = models.CharField(max_length=10, blank=True, default='')
    pcg_label = models.CharField(max_length=100, blank=True, default='')
    business_personal = models.CharField(max_length=10, default='unknown',
                                         choices=[('business', 'Business'),
                                                  ('personal', 'Personal'),
                                                  ('unknown', 'Unknown')])
    tva_deductible = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transaction_date', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'source_type', 'source_id'],
                name='unique_source_per_user',
            ),
        ]
        indexes = [
            models.Index(fields=['user', 'transaction_date']),
            models.Index(fields=['user', 'source_type']),
            models.Index(fields=['user', 'category']),
            models.Index(fields=['user', 'cluster']),
        ]

    def __str__(self):
        return f'{self.source_type}:{self.source_id} {self.vendor_name} {self.amount} {self.currency}'

    def save(self, *args, **kwargs):
        # Auto-compute vendor_name_normalized
        self.vendor_name_normalized = normalize_vendor(self.vendor_name)

        # Auto-compute completeness
        has_vendor = bool(self.vendor_name)
        has_amount = self.amount is not None
        has_date = self.transaction_date is not None

        if has_vendor and has_amount and has_date:
            self.completeness = 'complete'
        elif has_vendor or has_amount or has_date:
            self.completeness = 'partial'
        else:
            self.completeness = 'minimal'

        super().save(*args, **kwargs)


class BankFileImport(models.Model):
    class FileType(models.TextChoices):
        CSV = 'csv'
        OFX = 'ofx'
        QIF = 'qif'
        CAMT053 = 'camt053'

    class Status(models.TextChoices):
        PENDING = 'pending'
        PARSING = 'parsing'
        NEEDS_CONFIRMATION = 'needs_confirmation'
        PARSED = 'parsed'
        FAILED = 'failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                             related_name='bank_file_imports')
    file = models.FileField(upload_to='bank_imports/%Y/%m/', blank=True)
    file_type = models.CharField(max_length=10, choices=FileType.choices)
    bank_name = models.CharField(max_length=100, blank=True, default='')
    account_identifier = models.CharField(max_length=100, blank=True, default='')

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    rows_total = models.IntegerField(default=0)
    rows_imported = models.IntegerField(default=0)
    rows_skipped = models.IntegerField(default=0)
    parser_used = models.CharField(max_length=50, blank=True, default='')
    column_mapping = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default='')

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-uploaded_at']

    def __str__(self):
        return f'Import #{self.pk} ({self.file_type}) {self.bank_name} — {self.status}'
```

- [ ] **Step 4: Generate and run migration**

Run: `python manage.py makemigrations ai_agent && python manage.py migrate`
Expected: Migration created and applied successfully

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test ai_agent.tests.test_models -v 2`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add ai_agent/models.py ai_agent/tests/test_models.py ai_agent/migrations/
git commit -m "feat: add UnifiedTransaction, TransactionCluster, BankFileImport models"
```

---

## Task 3: Source Normalizers

**Files:**
- Create: `ai_agent/services/normalizers/__init__.py`
- Create: `ai_agent/services/normalizers/base.py`
- Create: `ai_agent/services/normalizers/stripe.py`
- Create: `ai_agent/services/normalizers/mollie.py`
- Create: `ai_agent/services/normalizers/paypal.py`
- Create: `ai_agent/services/normalizers/bank_api.py`
- Create: `ai_agent/services/normalizers/email.py`
- Create: `ai_agent/tests/test_normalizers.py`

- [ ] **Step 1: Write failing tests for normalizers**

```python
# ai_agent/tests/test_normalizers.py
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_agent.models import UnifiedTransaction
from ai_agent.services.normalizers.base import BaseNormalizer
from ai_agent.services.normalizers.stripe import StripeNormalizer
from ai_agent.services.normalizers.mollie import MollieNormalizer
from ai_agent.services.normalizers.paypal import PayPalNormalizer
from ai_agent.services.normalizers.bank_api import BankAPINormalizer
from ai_agent.services.normalizers.email import EmailNormalizer

User = get_user_model()


class StripeNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='s@test.com', password='test123')
        self.normalizer = StripeNormalizer()

    def test_normalize_charge(self):
        charge = MagicMock()
        charge.pk = 1
        charge.stripe_id = 'ch_abc123'
        charge.amount = 5000  # cents
        charge.currency = 'eur'
        charge.created_at_stripe = '2026-03-15T10:00:00Z'
        charge.description = 'Payment for order #123'
        charge.statement_descriptor = 'ACME CORP'
        charge.status = 'succeeded'
        charge.payment_method_type = 'card'

        ut = self.normalizer.normalize_charge(self.user, charge)
        self.assertEqual(ut.source_type, 'stripe')
        self.assertEqual(ut.source_id, 'ch_abc123')
        self.assertEqual(ut.direction, 'inflow')
        self.assertEqual(ut.category, 'revenue')
        self.assertEqual(ut.amount, Decimal('50.00'))
        self.assertEqual(ut.currency, 'EUR')
        self.assertEqual(ut.vendor_name, 'ACME CORP')
        self.assertEqual(ut.transaction_date, date(2026, 3, 15))

    def test_normalize_payout(self):
        payout = MagicMock()
        payout.pk = 2
        payout.stripe_id = 'po_xyz789'
        payout.amount = 10000  # cents
        payout.currency = 'eur'
        payout.arrival_date = '2026-03-17'
        payout.status = 'paid'

        ut = self.normalizer.normalize_payout(self.user, payout)
        self.assertEqual(ut.source_type, 'stripe')
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.category, 'transfer')
        self.assertEqual(ut.amount, Decimal('100.00'))


class MollieNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='m@test.com', password='test123')
        self.normalizer = MollieNormalizer()

    def test_normalize_payment(self):
        payment = MagicMock()
        payment.pk = 1
        payment.mollie_id = 'tr_abc123'
        payment.amount = Decimal('25.50')
        payment.currency = 'EUR'
        payment.paid_at = '2026-03-15T14:30:00+00:00'
        payment.created_at_mollie = '2026-03-15T14:25:00+00:00'
        payment.description = 'Order #456'
        payment.method = 'ideal'
        payment.status = 'paid'

        ut = self.normalizer.normalize_payment(self.user, payment)
        self.assertEqual(ut.source_type, 'mollie')
        self.assertEqual(ut.amount, Decimal('25.50'))
        self.assertEqual(ut.payment_method, 'ideal')
        self.assertEqual(ut.direction, 'inflow')


class PayPalNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='p@test.com', password='test123')
        self.normalizer = PayPalNormalizer()

    def test_normalize_transaction(self):
        tx = MagicMock()
        tx.pk = 1
        tx.paypal_id = 'PAY-123'
        tx.amount = Decimal('99.99')
        tx.currency = 'USD'
        tx.initiation_date = '2026-03-15T10:00:00Z'
        tx.description = 'Invoice payment'
        tx.fee = Decimal('2.99')
        tx.status = 'S'  # success

        ut = self.normalizer.normalize_transaction(self.user, tx)
        self.assertEqual(ut.source_type, 'paypal')
        self.assertEqual(ut.amount, Decimal('99.99'))
        self.assertEqual(ut.currency, 'USD')


class BankAPINormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='b@test.com', password='test123')
        self.normalizer = BankAPINormalizer()

    def test_normalize_debit(self):
        bt = MagicMock()
        bt.pk = 10
        bt.powens_transaction_id = 12345
        bt.value = Decimal('-49.99')
        bt.date = date(2026, 3, 17)
        bt.rdate = date(2026, 3, 15)
        bt.original_wording = 'CB*AMAZON PARIS 02'
        bt.simplified_wording = 'Amazon'
        bt.transaction_type = 'card'
        bt.original_currency = ''
        bt.original_value = None
        bt.account = MagicMock()
        bt.account.currency = 'EUR'

        ut = self.normalizer.normalize(self.user, bt)
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.amount, Decimal('49.99'))  # absolute value
        self.assertEqual(ut.transaction_date, date(2026, 3, 15))  # rdate preferred
        self.assertEqual(ut.vendor_name, 'CB*AMAZON PARIS 02')

    def test_normalize_credit(self):
        bt = MagicMock()
        bt.pk = 11
        bt.powens_transaction_id = 12346
        bt.value = Decimal('500.00')
        bt.date = date(2026, 3, 20)
        bt.rdate = None
        bt.original_wording = 'VIR STRIPE PAYOUT'
        bt.simplified_wording = 'Stripe'
        bt.transaction_type = 'transfer'
        bt.original_currency = ''
        bt.original_value = None
        bt.account = MagicMock()
        bt.account.currency = 'EUR'

        ut = self.normalizer.normalize(self.user, bt)
        self.assertEqual(ut.direction, 'inflow')
        self.assertEqual(ut.amount, Decimal('500.00'))
        self.assertEqual(ut.transaction_date, date(2026, 3, 20))  # fallback to date


class EmailNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='e@test.com', password='test123')
        self.normalizer = EmailNormalizer()

    def test_normalize_invoice(self):
        tx = MagicMock()
        tx.pk = 5
        tx.type = 'invoice'
        tx.vendor_name = 'OVH SAS'
        tx.amount = Decimal('14.39')
        tx.currency = 'EUR'
        tx.transaction_date = date(2026, 3, 1)
        tx.invoice_number = 'INV-2026-001'
        tx.order_number = ''
        tx.amount_tax_excl = Decimal('11.99')
        tx.tax_amount = Decimal('2.40')
        tx.tax_rate = Decimal('20.0')
        tx.payment_method = 'debit card'
        tx.payment_reference = ''
        tx.items = [{'name': 'VPS Cloud', 'quantity': 1, 'unit_price': 11.99}]
        tx.description = 'Monthly VPS hosting'
        tx.confidence = 0.95
        tx.status = 'complete'

        ut = self.normalizer.normalize(self.user, tx)
        self.assertEqual(ut.source_type, 'email')
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.category, 'expense_service')
        self.assertEqual(ut.reference, 'INV-2026-001')
        self.assertEqual(ut.amount_tax_excl, Decimal('11.99'))
        self.assertEqual(ut.items, [{'name': 'VPS Cloud', 'quantity': 1, 'unit_price': 11.99}])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test ai_agent.tests.test_normalizers -v 2`
Expected: ImportError — normalizer modules don't exist

- [ ] **Step 3: Implement BaseNormalizer**

```python
# ai_agent/services/normalizers/__init__.py
from .stripe import StripeNormalizer
from .mollie import MollieNormalizer
from .paypal import PayPalNormalizer
from .bank_api import BankAPINormalizer
from .email import EmailNormalizer

__all__ = [
    'StripeNormalizer', 'MollieNormalizer', 'PayPalNormalizer',
    'BankAPINormalizer', 'EmailNormalizer',
]
```

```python
# ai_agent/services/normalizers/base.py
"""Base normalizer interface for converting provider data to UnifiedTransaction."""
from ai_agent.models import UnifiedTransaction


class BaseNormalizer:
    """
    All normalizers return unsaved UnifiedTransaction instances.
    The caller is responsible for saving (allows dedup checks first).
    """

    def _build(self, user, **kwargs) -> UnifiedTransaction:
        """Create an unsaved UnifiedTransaction with the given fields."""
        return UnifiedTransaction(user=user, **kwargs)
```

- [ ] **Step 4: Implement StripeNormalizer**

```python
# ai_agent/services/normalizers/stripe.py
from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class StripeNormalizer(BaseNormalizer):

    def normalize_charge(self, user, charge) -> 'UnifiedTransaction':
        amount_decimal = Decimal(str(charge.amount)) / Decimal('100')
        tx_date = self._parse_date(charge.created_at_stripe)
        vendor = charge.statement_descriptor or charge.description or ''

        return self._build(
            user=user,
            source_type='stripe',
            source_id=charge.stripe_id,
            direction='inflow',
            category='revenue',
            amount=amount_decimal,
            currency=(charge.currency or 'eur').upper(),
            transaction_date=tx_date,
            vendor_name=vendor,
            description=charge.description or '',
            payment_method=getattr(charge, 'payment_method_type', '') or '',
            confidence=0.95,
        )

    def normalize_payout(self, user, payout) -> 'UnifiedTransaction':
        amount_decimal = Decimal(str(payout.amount)) / Decimal('100')
        tx_date = self._parse_date(payout.arrival_date)

        return self._build(
            user=user,
            source_type='stripe',
            source_id=payout.stripe_id,
            direction='outflow',
            category='transfer',
            amount=amount_decimal,
            currency=(payout.currency or 'eur').upper(),
            transaction_date=tx_date,
            vendor_name='Stripe Payout',
            description=f'Payout {payout.stripe_id}',
            confidence=0.99,
        )

    def _parse_date(self, value) -> date_type | None:
        if not value:
            return None
        if isinstance(value, date_type):
            return value
        s = str(value)[:10]
        try:
            return date_type.fromisoformat(s)
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 5: Implement MollieNormalizer**

```python
# ai_agent/services/normalizers/mollie.py
from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class MollieNormalizer(BaseNormalizer):

    def normalize_payment(self, user, payment) -> 'UnifiedTransaction':
        amount = payment.amount if isinstance(payment.amount, Decimal) else Decimal(str(payment.amount))
        tx_date = self._parse_date(payment.paid_at) or self._parse_date(payment.created_at_mollie)

        return self._build(
            user=user,
            source_type='mollie',
            source_id=payment.mollie_id,
            direction='inflow',
            category='revenue',
            amount=amount,
            currency=(payment.currency or 'EUR').upper(),
            transaction_date=tx_date,
            vendor_name=payment.description or '',
            description=payment.description or '',
            payment_method=payment.method or '',
            confidence=0.95,
        )

    def _parse_date(self, value) -> date_type | None:
        if not value:
            return None
        if isinstance(value, date_type):
            return value
        s = str(value)[:10]
        try:
            return date_type.fromisoformat(s)
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 6: Implement PayPalNormalizer**

```python
# ai_agent/services/normalizers/paypal.py
from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class PayPalNormalizer(BaseNormalizer):

    def normalize_transaction(self, user, tx) -> 'UnifiedTransaction':
        amount = tx.amount if isinstance(tx.amount, Decimal) else Decimal(str(tx.amount))
        tx_date = self._parse_date(tx.initiation_date)

        # PayPal: positive = received, negative = sent
        if amount >= 0:
            direction = 'inflow'
            category = 'revenue'
        else:
            direction = 'outflow'
            category = 'other'
            amount = abs(amount)

        return self._build(
            user=user,
            source_type='paypal',
            source_id=tx.paypal_id,
            direction=direction,
            category=category,
            amount=amount,
            currency=(tx.currency or 'USD').upper(),
            transaction_date=tx_date,
            vendor_name=tx.description or '',
            description=tx.description or '',
            confidence=0.90,
        )

    def _parse_date(self, value) -> date_type | None:
        if not value:
            return None
        if isinstance(value, date_type):
            return value
        s = str(value)[:10]
        try:
            return date_type.fromisoformat(s)
        except (ValueError, TypeError):
            return None
```

- [ ] **Step 7: Implement BankAPINormalizer**

```python
# ai_agent/services/normalizers/bank_api.py
from decimal import Decimal

from .base import BaseNormalizer


class BankAPINormalizer(BaseNormalizer):

    def normalize(self, user, bt) -> 'UnifiedTransaction':
        value = bt.value if isinstance(bt.value, Decimal) else Decimal(str(bt.value))

        if value < 0:
            direction = 'outflow'
            amount = abs(value)
        else:
            direction = 'inflow'
            amount = value

        # Prefer rdate (card swipe date) over date (booking date)
        tx_date = bt.rdate or bt.date

        currency = (bt.original_currency or '').upper()
        if not currency and bt.account:
            currency = getattr(bt.account, 'currency', 'EUR') or 'EUR'
        currency = currency.upper() if currency else 'EUR'

        return self._build(
            user=user,
            source_type='bank_api',
            source_id=str(bt.powens_transaction_id),
            direction=direction,
            category='other',  # enrichment agent will classify later
            amount=amount,
            currency=currency,
            transaction_date=tx_date,
            vendor_name=bt.original_wording or bt.simplified_wording or '',
            description=bt.simplified_wording or bt.original_wording or '',
            payment_method=bt.transaction_type or '',
            confidence=0.99,  # bank data is authoritative
        )
```

- [ ] **Step 8: Implement EmailNormalizer**

```python
# ai_agent/services/normalizers/email.py
from decimal import Decimal

from .base import BaseNormalizer


# Map email transaction types to unified categories
_TYPE_TO_CATEGORY = {
    'invoice': 'expense_service',
    'receipt': 'expense_goods',
    'order': 'expense_goods',
    'payment': 'other',
    'shipping': 'expense_shipping',
    'refund': 'refund',
    'cancellation': 'refund',
    'subscription': 'expense_service',
    'other': 'other',
}


class EmailNormalizer(BaseNormalizer):

    def normalize(self, user, tx) -> 'UnifiedTransaction':
        category = _TYPE_TO_CATEGORY.get(tx.type, 'other')
        amount = tx.amount if isinstance(tx.amount, Decimal) else (
            Decimal(str(tx.amount)) if tx.amount is not None else None
        )

        # Most email transactions are expenses (things the user bought)
        direction = 'outflow'
        if tx.type in ('refund', 'cancellation'):
            direction = 'inflow'

        reference = tx.invoice_number or tx.order_number or ''
        if tx.invoice_number and tx.order_number:
            reference = f'{tx.invoice_number} / {tx.order_number}'

        return self._build(
            user=user,
            source_type='email',
            source_id=f'email_tx_{tx.pk}',
            direction=direction,
            category=category,
            amount=amount,
            currency=(tx.currency or 'EUR').upper(),
            transaction_date=tx.transaction_date,
            vendor_name=tx.vendor_name or '',
            description=tx.description or '',
            reference=reference,
            payment_method=tx.payment_method or '',
            items=tx.items or [],
            amount_tax_excl=tx.amount_tax_excl,
            tax_amount=tx.tax_amount,
            tax_rate=tx.tax_rate,
            confidence=tx.confidence or 0.5,
        )
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `python manage.py test ai_agent.tests.test_normalizers -v 2`
Expected: All tests PASS

- [ ] **Step 10: Commit**

```bash
git add ai_agent/services/normalizers/ ai_agent/tests/test_normalizers.py
git commit -m "feat: add source normalizers (Stripe, Mollie, PayPal, Bank, Email)"
```

---

## Task 4: Base Agent Framework (Worker/Verifier/Cleaner Pattern)

**Files:**
- Create: `ai_agent/services/agents/__init__.py`
- Create: `ai_agent/services/agents/base.py`
- Create: `ai_agent/tests/test_agents.py`

- [ ] **Step 1: Write failing tests for BaseAgent**

```python
# ai_agent/tests/test_agents.py
from unittest.mock import patch, MagicMock, AsyncMock
import asyncio

from django.test import TestCase

from ai_agent.services.agents.base import BaseAgent, AgentResult, PhaseState


class PhaseStateTest(TestCase):

    def test_immutable_transition(self):
        state = PhaseState(phase='enrichment', turn_count=0, items_total=10)
        new_state = state.transition(turn_count=1, reason='next_turn')
        self.assertEqual(state.turn_count, 0)  # original unchanged
        self.assertEqual(new_state.turn_count, 1)
        self.assertEqual(new_state.transition_reason, 'next_turn')

    def test_recovery_guards(self):
        state = PhaseState(phase='correlation', turn_count=0, items_total=5)
        self.assertTrue(state.can_retry_rate_limit)
        state2 = state.transition(rate_limit_retries=3, reason='rate_limit')
        self.assertFalse(state2.can_retry_rate_limit)

    def test_max_turns(self):
        state = PhaseState(phase='test', turn_count=19, items_total=1)
        self.assertFalse(state.has_turns_remaining)


class BaseAgentTest(TestCase):

    @patch('ai_agent.services.agents.base.anthropic')
    def test_call_llm_with_retry_rate_limit(self, mock_anthropic):
        """Rate limit error should be retried with backoff."""
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = [
            real_anthropic.RateLimitError(
                message='rate limited',
                response=MagicMock(status_code=429, headers={}),
                body={'error': {'message': 'rate limited', 'type': 'rate_limit_error'}},
            ),
            MagicMock(
                content=[MagicMock(type='text', text='ok')],
                stop_reason='end_turn',
                usage=MagicMock(input_tokens=100, output_tokens=50),
            ),
        ]
        agent = BaseAgent(client=mock_client, model='claude-haiku-4-5-20251001')
        result = agent._call_llm_sync(
            system='test', messages=[{'role': 'user', 'content': 'hi'}]
        )
        self.assertEqual(mock_client.messages.create.call_count, 2)

    @patch('ai_agent.services.agents.base.anthropic')
    def test_circuit_breaker_opens(self, mock_anthropic):
        """3 consecutive failures should open the circuit breaker."""
        import anthropic as real_anthropic
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = real_anthropic.APIError(
            message='server error',
            response=MagicMock(status_code=500, headers={}),
            body={'error': {'message': 'server error', 'type': 'api_error'}},
        )
        agent = BaseAgent(client=mock_client, model='claude-haiku-4-5-20251001')
        # After 3 failures, circuit breaker should be open
        for _ in range(3):
            try:
                agent._call_llm_sync(
                    system='test', messages=[{'role': 'user', 'content': 'hi'}]
                )
            except Exception:
                pass
        self.assertFalse(agent.circuit_breaker.can_call())
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test ai_agent.tests.test_agents -v 2`
Expected: ImportError — agents.base doesn't exist

- [ ] **Step 3: Implement BaseAgent with PhaseState and recovery paths**

```python
# ai_agent/services/agents/__init__.py
```

```python
# ai_agent/services/agents/base.py
"""
Base agent framework: Worker/Verifier/Cleaner pattern with recovery paths.

Inspired by Claude Code architecture (rapport §2.1):
- Immutable state rebuilt at each transition
- Named recovery paths with anti-loop guards
- Circuit breaker per agent
- Model selection: Haiku for simple tasks, Sonnet for complex reasoning
"""
import json
import logging
import threading
import time
from dataclasses import dataclass, field, replace
from typing import Any

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

MAX_RETRIES = getattr(settings, 'AI_MAX_RETRIES', 3)
RETRY_BASE_DELAY = getattr(settings, 'AI_RETRY_BASE_DELAY', 2)
MAX_TURNS_PER_PHASE = 20
MAX_RATE_LIMIT_RETRIES = 3
MAX_TOOL_ERROR_RETRIES = 3


@dataclass(frozen=True)
class PhaseState:
    """Immutable state rebuilt at each transition (rapport §2.1)."""
    phase: str
    turn_count: int = 0
    items_total: int = 0
    items_processed: int = 0
    items_failed: tuple = ()

    # Recovery guards
    rate_limit_retries: int = 0
    token_overflow_retries: int = 0
    tool_error_retries: int = 0
    has_attempted_compaction: bool = False

    # Transition info
    transition_reason: str = ''

    @property
    def can_retry_rate_limit(self) -> bool:
        return self.rate_limit_retries < MAX_RATE_LIMIT_RETRIES

    @property
    def can_retry_tool_error(self) -> bool:
        return self.tool_error_retries < MAX_TOOL_ERROR_RETRIES

    @property
    def has_turns_remaining(self) -> bool:
        return self.turn_count < MAX_TURNS_PER_PHASE

    def transition(self, reason: str = '', **kwargs) -> 'PhaseState':
        """Create a new state with updated fields."""
        updates = {k: v for k, v in kwargs.items() if v is not None}
        updates['transition_reason'] = reason
        return replace(self, **updates)


@dataclass
class AgentResult:
    """Result from an agent phase execution."""
    success: bool
    items_processed: int = 0
    items_failed: int = 0
    stats: dict = field(default_factory=dict)
    errors: list = field(default_factory=list)


class CircuitBreaker:
    """
    Stops API calls after consecutive failures (rapport §2.1).
    3 states: CLOSED → OPEN → HALF_OPEN.
    """
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

    def can_call(self) -> bool:
        with self._lock:
            if self.state == self.CLOSED:
                return True
            if self.state == self.OPEN:
                if self.last_failure_time and (time.time() - self.last_failure_time >= self.recovery_timeout):
                    self.state = self.HALF_OPEN
                    return True
                return False
            return self.state == self.HALF_OPEN

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
                    f'[CircuitBreaker] OPEN after {self.failure_count} failures, '
                    f'blocking for {self.recovery_timeout}s'
                )


class BaseAgent:
    """
    Base class for all pipeline agents.

    Each agent follows the Worker/Verifier/Cleaner pattern:
    - Worker: does the main LLM work
    - Verifier: independent LLM call reviewing worker output (fresh context)
    - Cleaner: post-processing cleanup (dedup, validation)

    Subclasses implement:
    - run_worker(state, context) → list of results
    - run_verifier(results) → list of corrections
    - run_cleaner(results, corrections) → cleaned results
    """

    def __init__(self, client=None, model='claude-haiku-4-5-20251001'):
        self.client = client or anthropic.Anthropic(
            api_key=getattr(settings, 'ANTHROPIC_API_KEY', None)
        )
        self.model = model
        self.circuit_breaker = CircuitBreaker()

    def execute(self, user, context: dict) -> AgentResult:
        """
        Run the full Worker → Verifier → Cleaner pipeline.
        Returns AgentResult with stats.
        """
        logger.info(f'[{self.__class__.__name__}] Starting execution')

        # Step 1: Worker produces results
        try:
            worker_results = self.run_worker(user, context)
        except Exception as e:
            logger.error(f'[{self.__class__.__name__}] Worker failed: {e}')
            return AgentResult(success=False, errors=[str(e)])

        # Step 2: Verifier reviews (fresh context, no self-confirmation)
        try:
            corrections = self.run_verifier(user, worker_results, context)
        except Exception as e:
            logger.warning(f'[{self.__class__.__name__}] Verifier failed: {e}, using worker results as-is')
            corrections = []

        # Step 3: Cleaner applies corrections and validates
        try:
            cleaned = self.run_cleaner(user, worker_results, corrections, context)
        except Exception as e:
            logger.warning(f'[{self.__class__.__name__}] Cleaner failed: {e}, using worker results')
            cleaned = worker_results

        return AgentResult(
            success=True,
            items_processed=len(cleaned),
            stats={'worker_results': len(worker_results), 'corrections': len(corrections)},
        )

    def run_worker(self, user, context: dict) -> list:
        raise NotImplementedError

    def run_verifier(self, user, results: list, context: dict) -> list:
        return []  # default: no verification

    def run_cleaner(self, user, results: list, corrections: list, context: dict) -> list:
        return results  # default: no cleaning

    def _call_llm_sync(self, system: str, messages: list, tools: list | None = None,
                       max_tokens: int = 4096, model: str | None = None) -> Any:
        """
        Call the Anthropic API with retry on rate limit errors.
        Uses circuit breaker to prevent cascading failures.
        """
        if not self.circuit_breaker.can_call():
            raise RuntimeError('Circuit breaker is OPEN — too many consecutive failures')

        use_model = model or self.model
        kwargs = {
            'model': use_model,
            'max_tokens': max_tokens,
            'system': system,
            'messages': messages,
        }
        if tools:
            kwargs['tools'] = tools

        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.messages.create(**kwargs)
                self.circuit_breaker.record_success()
                return response
            except anthropic.RateLimitError:
                self.circuit_breaker.record_failure()
                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f'Rate limited, retrying in {delay}s (attempt {attempt + 1})')
                    time.sleep(delay)
                else:
                    raise
            except anthropic.APIError as e:
                self.circuit_breaker.record_failure()
                if getattr(e, 'status_code', 0) == 529 and attempt < MAX_RETRIES - 1:
                    delay = RETRY_BASE_DELAY * (2 ** attempt)
                    logger.warning(f'API overloaded, retrying in {delay}s')
                    time.sleep(delay)
                else:
                    raise

    def _extract_text(self, response) -> str:
        """Extract text content from an Anthropic API response."""
        return ''.join(
            block.text for block in response.content
            if hasattr(block, 'text') and block.text
        )

    def _extract_json(self, text: str) -> Any:
        """Extract JSON from LLM response text (handles markdown fences)."""
        import re

        if not text:
            return None

        stripped = text.strip()

        # Try direct parse
        for start_char in ('{', '['):
            if stripped.startswith(start_char):
                try:
                    return json.loads(stripped)
                except json.JSONDecodeError:
                    pass

        # Try finding JSON in text
        for pattern in [r'\{[\s\S]*\}', r'\[[\s\S]*\]']:
            match = re.search(pattern, text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Try markdown code block
        code_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
        if code_match:
            try:
                return json.loads(code_match.group(1))
            except json.JSONDecodeError:
                pass

        return None

    def _run_agentic_loop(self, system: str, messages: list, tools: list,
                          tool_handlers: dict, max_iterations: int = 15,
                          model: str | None = None) -> tuple[list, dict]:
        """
        Run a tool-use agentic loop (rapport §2.1).

        Returns (messages, stats) where messages is the full conversation
        and stats tracks tool calls and results.
        """
        stats = {'api_calls': 0, 'tool_calls': 0, 'iterations': 0}
        messages = list(messages)  # copy

        response = self._call_llm_sync(
            system=system, messages=messages, tools=tools, model=model,
        )
        stats['api_calls'] += 1

        for iteration in range(max_iterations):
            stats['iterations'] = iteration + 1

            if response.stop_reason != 'tool_use':
                break

            # Execute tool calls
            tool_results = []
            for block in response.content:
                if block.type != 'tool_use':
                    continue

                stats['tool_calls'] += 1
                handler = tool_handlers.get(block.name)

                if handler:
                    try:
                        result = handler(block.input)
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps(result, default=str),
                        })
                    except Exception as e:
                        logger.error(f'Tool error {block.name}: {e}')
                        tool_results.append({
                            'type': 'tool_result',
                            'tool_use_id': block.id,
                            'content': json.dumps({'error': str(e)}),
                            'is_error': True,
                        })
                else:
                    tool_results.append({
                        'type': 'tool_result',
                        'tool_use_id': block.id,
                        'content': json.dumps({'error': f'Unknown tool: {block.name}'}),
                        'is_error': True,
                    })

            messages.append({'role': 'assistant', 'content': response.content})
            messages.append({'role': 'user', 'content': tool_results})

            response = self._call_llm_sync(
                system=system, messages=messages, tools=tools, model=model,
            )
            stats['api_calls'] += 1

        return messages, stats
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python manage.py test ai_agent.tests.test_agents -v 2`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add ai_agent/services/agents/ ai_agent/tests/test_agents.py
git commit -m "feat: add base agent framework with Worker/Verifier/Cleaner pattern and recovery paths"
```

---

## Task 5: Specialized Agents — Ingestion, Enrichment, Correlation, Computation, Verification

**Files:**
- Create: `ai_agent/services/agents/ingestion.py`
- Create: `ai_agent/services/agents/enrichment.py`
- Create: `ai_agent/services/agents/correlation.py`
- Create: `ai_agent/services/agents/computation.py`
- Create: `ai_agent/services/agents/verification.py`
- Create: `ai_agent/services/tools.py`

- [ ] **Step 1: Implement LLM tools for the agents**

```python
# ai_agent/services/tools.py
"""
LLM tool definitions and handlers for the agentic pipeline.

Each tool has:
- Schema (JSON Schema for the LLM)
- Handler (Python function that executes the tool)
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.normalization import normalize_vendor, vendors_match

logger = logging.getLogger(__name__)


# ============================================================
# Tool Schemas (sent to the LLM)
# ============================================================

THINK_TOOL = {
    "name": "think",
    "description": (
        "Use this tool to plan your approach BEFORE taking action. "
        "Write your analysis and action plan. This is mandatory before "
        "any create/enrich/cluster operation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your analysis and planned action.",
            },
        },
        "required": ["thought"],
    },
}

SEARCH_TRANSACTIONS_TOOL = {
    "name": "search_transactions",
    "description": (
        "Search existing UnifiedTransactions by vendor, amount, date, reference, "
        "or source type. Use BEFORE deciding if a new transaction should be created "
        "or linked to an existing one. Vendor search is fuzzy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "string", "description": "Vendor name (fuzzy match)."},
            "amount": {"type": "number", "description": "Exact amount to match."},
            "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD, inclusive)."},
            "date_to": {"type": "string", "description": "End date (YYYY-MM-DD, inclusive)."},
            "reference": {"type": "string", "description": "Invoice/order/payment reference."},
            "source_type": {"type": "string", "description": "Filter by source type."},
            "limit": {"type": "integer", "description": "Max results (default 20)."},
        },
    },
}

CREATE_CLUSTER_TOOL = {
    "name": "create_cluster",
    "description": (
        "Create a new TransactionCluster grouping related transactions. "
        "Provide a human-readable label, cluster type, and the IDs of "
        "transactions to include. Explain your reasoning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Human-readable cluster label."},
            "cluster_type": {
                "type": "string",
                "enum": ["sale", "purchase", "subscription", "refund",
                         "transfer", "salary", "tax_payment", "other"],
            },
            "transaction_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "IDs of UnifiedTransactions to include.",
            },
            "reasoning": {"type": "string", "description": "Why these transactions are related."},
        },
        "required": ["label", "cluster_type", "transaction_ids", "reasoning"],
    },
}

ADD_TO_CLUSTER_TOOL = {
    "name": "add_to_cluster",
    "description": (
        "Add a transaction to an existing cluster. Specify the evidence role: "
        "confirmation (same data, different source), enrichment (adds missing data), "
        "or contradiction (conflicts with existing data)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cluster_id": {"type": "integer", "description": "Cluster ID to add to."},
            "transaction_id": {"type": "integer", "description": "Transaction ID to add."},
            "evidence_role": {
                "type": "string",
                "enum": ["confirmation", "enrichment", "contradiction"],
            },
            "reasoning": {"type": "string"},
        },
        "required": ["cluster_id", "transaction_id", "evidence_role"],
    },
}

ENRICH_TRANSACTION_TOOL = {
    "name": "enrich_transaction",
    "description": (
        "Update fields on an existing UnifiedTransaction. Use when new data "
        "is available (from email body, cross-reference, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "fields": {
                "type": "object",
                "description": "Fields to update: category, pcg_code, pcg_label, "
                               "business_personal, tva_deductible, vendor_type, "
                               "tax_rate, tax_amount, amount_tax_excl, description.",
            },
        },
        "required": ["transaction_id", "fields"],
    },
}

FLAG_CONTRADICTION_TOOL = {
    "name": "flag_contradiction",
    "description": (
        "Flag a contradiction between two data points for human review. "
        "Example: email says €50 but Stripe says €45."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "cluster_id": {"type": "integer", "description": "Related cluster (optional)."},
            "description": {"type": "string", "description": "What is contradictory and why."},
        },
        "required": ["transaction_id", "description"],
    },
}

CLASSIFY_EXPENSE_TOOL = {
    "name": "classify_expense",
    "description": (
        "Classify a transaction with PCG code, business/personal, TVA deductibility. "
        "Use for bank transactions and email expenses."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "pcg_code": {"type": "string", "description": "PCG code (606, 613, 615, 625, 626, 627, 628, 791...)."},
            "pcg_label": {"type": "string", "description": "Human-readable label."},
            "category": {
                "type": "string",
                "enum": ["revenue", "expense_service", "expense_goods", "expense_shipping",
                         "purchase_cost", "tax", "fee", "refund", "transfer", "salary", "other"],
            },
            "business_personal": {"type": "string", "enum": ["business", "personal", "unknown"]},
            "tva_deductible": {"type": "boolean"},
            "confidence": {"type": "number", "description": "0.0-1.0"},
            "reasoning": {"type": "string"},
        },
        "required": ["transaction_id", "pcg_code", "pcg_label", "category",
                      "business_personal", "tva_deductible", "confidence"],
    },
}


# ============================================================
# Tool Handlers (executed by the agent framework)
# ============================================================

def make_tool_handlers(user):
    """Create tool handlers bound to a specific user."""

    def handle_think(params):
        logger.info(f'[Think] {params.get("thought", "")[:300]}')
        return {"ok": True}

    def handle_search_transactions(params):
        qs = UnifiedTransaction.objects.filter(user=user)

        if params.get('vendor_name'):
            normalized = normalize_vendor(params['vendor_name'])
            if normalized:
                qs = qs.filter(vendor_name_normalized__icontains=normalized)

        if params.get('amount') is not None:
            try:
                amt = Decimal(str(params['amount']))
                qs = qs.filter(amount=amt)
            except (InvalidOperation, ValueError):
                pass

        if params.get('date_from'):
            qs = qs.filter(transaction_date__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(transaction_date__lte=params['date_to'])

        if params.get('reference'):
            qs = qs.filter(reference__icontains=params['reference'])
        if params.get('source_type'):
            qs = qs.filter(source_type=params['source_type'])

        limit = min(params.get('limit', 20), 50)
        results = qs[:limit]

        return [
            {
                'id': t.id,
                'source_type': t.source_type,
                'source_id': t.source_id,
                'direction': t.direction,
                'category': t.category,
                'amount': str(t.amount) if t.amount else None,
                'currency': t.currency,
                'transaction_date': str(t.transaction_date) if t.transaction_date else None,
                'vendor_name': t.vendor_name,
                'vendor_name_normalized': t.vendor_name_normalized,
                'description': t.description[:100],
                'reference': t.reference,
                'confidence': t.confidence,
                'cluster_id': t.cluster_id,
                'evidence_role': t.evidence_role,
            }
            for t in results
        ]

    def handle_create_cluster(params):
        tx_ids = params.get('transaction_ids', [])
        txs = UnifiedTransaction.objects.filter(user=user, id__in=tx_ids)

        if txs.count() == 0:
            return {"error": "No valid transaction IDs provided"}

        cluster = TransactionCluster.objects.create(
            user=user,
            label=params['label'],
            cluster_type=params['cluster_type'],
            match_reasoning=params.get('reasoning', ''),
            created_by='ai_agent',
        )

        txs.update(cluster=cluster)
        cluster.recalculate_metrics()

        return {
            "cluster_id": cluster.id,
            "label": cluster.label,
            "transactions_count": txs.count(),
            "margin": str(cluster.margin),
        }

    def handle_add_to_cluster(params):
        try:
            cluster = TransactionCluster.objects.get(id=params['cluster_id'], user=user)
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except (TransactionCluster.DoesNotExist, UnifiedTransaction.DoesNotExist) as e:
            return {"error": str(e)}

        tx.cluster = cluster
        tx.evidence_role = params.get('evidence_role', 'confirmation')
        tx.save()

        cluster.recalculate_metrics()

        return {
            "cluster_id": cluster.id,
            "transaction_id": tx.id,
            "evidence_role": tx.evidence_role,
            "cluster_transactions_count": cluster.transactions.count(),
        }

    def handle_enrich_transaction(params):
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except UnifiedTransaction.DoesNotExist:
            return {"error": f"Transaction {params['transaction_id']} not found"}

        fields = params.get('fields', {})
        allowed_fields = {
            'category', 'pcg_code', 'pcg_label', 'business_personal',
            'tva_deductible', 'description', 'tax_rate', 'tax_amount',
            'amount_tax_excl', 'payment_method', 'reference',
        }

        updated = []
        for field_name, value in fields.items():
            if field_name in allowed_fields:
                if field_name in ('tax_rate', 'tax_amount', 'amount_tax_excl'):
                    try:
                        value = Decimal(str(value))
                    except (InvalidOperation, ValueError):
                        continue
                setattr(tx, field_name, value)
                updated.append(field_name)

        if updated:
            tx.save()

        return {"transaction_id": tx.id, "updated_fields": updated}

    def handle_classify_expense(params):
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except UnifiedTransaction.DoesNotExist:
            return {"error": f"Transaction {params['transaction_id']} not found"}

        tx.pcg_code = params.get('pcg_code', tx.pcg_code)
        tx.pcg_label = params.get('pcg_label', tx.pcg_label)
        tx.category = params.get('category', tx.category)
        tx.business_personal = params.get('business_personal', tx.business_personal)
        tx.tva_deductible = params.get('tva_deductible', tx.tva_deductible)
        tx.confidence = max(tx.confidence, params.get('confidence', 0))
        tx.save()

        return {
            "transaction_id": tx.id,
            "pcg_code": tx.pcg_code,
            "category": tx.category,
            "business_personal": tx.business_personal,
        }

    def handle_flag_contradiction(params):
        logger.warning(
            f'[Contradiction] TX #{params["transaction_id"]}: {params["description"]}'
        )
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
            tx.evidence_role = 'contradiction'
            tx.save()
        except UnifiedTransaction.DoesNotExist:
            pass

        return {
            "flagged": True,
            "transaction_id": params['transaction_id'],
            "description": params['description'],
        }

    return {
        'think': handle_think,
        'search_transactions': handle_search_transactions,
        'create_cluster': handle_create_cluster,
        'add_to_cluster': handle_add_to_cluster,
        'enrich_transaction': handle_enrich_transaction,
        'classify_expense': handle_classify_expense,
        'flag_contradiction': handle_flag_contradiction,
    }
```

- [ ] **Step 2: Implement IngestionAgent (no LLM)**

```python
# ai_agent/services/agents/ingestion.py
"""
Ingestion Agent — no LLM, runs normalizers per provider.

Fetches data from all connected sources and creates UnifiedTransactions.
Handles deduplication via unique constraint (user + source_type + source_id).
"""
import logging

from django.db import IntegrityError

from ai_agent.models import UnifiedTransaction
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.normalizers import (
    StripeNormalizer, MollieNormalizer, PayPalNormalizer,
    BankAPINormalizer, EmailNormalizer,
)

logger = logging.getLogger(__name__)


class IngestionAgent(BaseAgent):
    """No LLM needed — pure Python normalizer execution."""

    def execute(self, user, context: dict) -> AgentResult:
        stats = {'created': 0, 'skipped': 0, 'errors': 0, 'per_source': {}}
        errors = []

        normalizer_configs = self._get_normalizer_configs(user)

        for source_name, config in normalizer_configs.items():
            source_stats = {'created': 0, 'skipped': 0}
            normalizer = config['normalizer']
            queryset = config['queryset']
            normalize_fn = config['normalize_fn']

            for obj in queryset:
                try:
                    ut = normalize_fn(normalizer, user, obj)
                    ut.save()
                    source_stats['created'] += 1
                except IntegrityError:
                    source_stats['skipped'] += 1  # duplicate
                except Exception as e:
                    logger.error(f'[Ingestion] Error normalizing {source_name} #{getattr(obj, "pk", "?")}: {e}')
                    stats['errors'] += 1
                    errors.append(f'{source_name}: {e}')

            stats['per_source'][source_name] = source_stats
            stats['created'] += source_stats['created']
            stats['skipped'] += source_stats['skipped']

        logger.info(f'[Ingestion] Done: {stats["created"]} created, {stats["skipped"]} skipped')
        return AgentResult(
            success=True,
            items_processed=stats['created'],
            stats=stats,
            errors=errors,
        )

    def _get_normalizer_configs(self, user) -> dict:
        configs = {}

        # Stripe charges
        try:
            from stripe_provider.models import StripeCharge
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='stripe')
                .values_list('source_id', flat=True)
            )
            charges = StripeCharge.objects.filter(connection__user=user).exclude(
                stripe_id__in=existing_ids
            )
            if charges.exists():
                configs['stripe_charges'] = {
                    'normalizer': StripeNormalizer(),
                    'queryset': charges,
                    'normalize_fn': lambda n, u, obj: n.normalize_charge(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Stripe not available: {e}')

        # Mollie payments
        try:
            from mollie_provider.models import MolliePayment
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='mollie')
                .values_list('source_id', flat=True)
            )
            payments = MolliePayment.objects.filter(
                connection__user=user, status__in=['paid', 'open', 'authorized']
            ).exclude(mollie_id__in=existing_ids)
            if payments.exists():
                configs['mollie_payments'] = {
                    'normalizer': MollieNormalizer(),
                    'queryset': payments,
                    'normalize_fn': lambda n, u, obj: n.normalize_payment(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Mollie not available: {e}')

        # PayPal transactions
        try:
            from paypal_provider.models import PayPalTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='paypal')
                .values_list('source_id', flat=True)
            )
            txs = PayPalTransaction.objects.filter(
                connection__user=user
            ).exclude(paypal_id__in=existing_ids)
            if txs.exists():
                configs['paypal_transactions'] = {
                    'normalizer': PayPalNormalizer(),
                    'queryset': txs,
                    'normalize_fn': lambda n, u, obj: n.normalize_transaction(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] PayPal not available: {e}')

        # Bank API transactions
        try:
            from banking.models import BankTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='bank_api')
                .values_list('source_id', flat=True)
            )
            bank_txs = BankTransaction.objects.filter(user=user).exclude(
                powens_transaction_id__in=[int(x) for x in existing_ids if x.isdigit()]
            )
            if bank_txs.exists():
                configs['bank_api'] = {
                    'normalizer': BankAPINormalizer(),
                    'queryset': bank_txs,
                    'normalize_fn': lambda n, u, obj: n.normalize(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Bank API not available: {e}')

        # Email transactions
        try:
            from emails.models import Transaction as EmailTransaction
            existing_ids = set(
                UnifiedTransaction.objects.filter(user=user, source_type='email')
                .values_list('source_id', flat=True)
            )
            email_txs = EmailTransaction.objects.filter(
                user=user, status='complete'
            ).exclude(pk__in=[int(x.replace('email_tx_', '')) for x in existing_ids if x.startswith('email_tx_')])
            if email_txs.exists():
                configs['email'] = {
                    'normalizer': EmailNormalizer(),
                    'queryset': email_txs,
                    'normalize_fn': lambda n, u, obj: n.normalize(u, obj),
                }
        except (ImportError, Exception) as e:
            logger.debug(f'[Ingestion] Email not available: {e}')

        return configs
```

- [ ] **Step 3: Implement EnrichmentAgent (Haiku worker, Haiku verifier)**

```python
# ai_agent/services/agents/enrichment.py
"""
Enrichment Agent — classifies expenses with PCG codes, vendor types, TVA.

Worker: Sonnet (complex accounting reasoning)
Verifier: Haiku (simple consistency check)
"""
import json
import logging

from django.conf import settings

from ai_agent.models import UnifiedTransaction
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.tools import (
    THINK_TOOL, CLASSIFY_EXPENSE_TOOL, ENRICH_TRANSACTION_TOOL,
    make_tool_handlers,
)

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = (
    "You are a French accounting expert (expert-comptable) classifying financial transactions.\n\n"
    "For each transaction, you MUST:\n"
    "1. Call 'think' to analyze the transaction and plan your classification.\n"
    "2. Call 'classify_expense' with your classification.\n\n"
    "Classification rules:\n"
    "- PCG codes: 606=achats marchandises, 611=sous-traitance, 613=locations, "
    "615=services numériques/hébergement, 616=assurances, 623=publicité, "
    "625=déplacements/missions/réceptions, 626=frais postaux/télécom, "
    "627=services bancaires/commissions, 628=divers (abonnements), "
    "641=rémunérations personnel, 791=transferts de charges.\n"
    "- business_personal: 'business' if clearly professional, 'personal' if clearly personal, "
    "'unknown' if ambiguous (e.g. Uber Eats could be either).\n"
    "- tva_deductible: true for business expenses from FR/EU vendors. "
    "false for personal, non-EU vendors (US SaaS = no TVA), or when unsure.\n"
    "- Category: match to the best category based on the vendor and description.\n\n"
    "Process ALL transactions in the batch. Be efficient."
)

ENRICHMENT_VERIFIER_PROMPT = (
    "Review these expense classifications for consistency. ONLY flag CLEAR errors:\n"
    "- PCG code doesn't match the vendor type (e.g. hosting classified as 625 instead of 615)\n"
    "- TVA marked deductible for a US vendor\n"
    "- Business expense classified as personal when vendor is clearly professional\n\n"
    "Be CONSERVATIVE. Only correct if 100% certain.\n\n"
    "Classifications:\n{classifications}\n\n"
    "Return corrections: [{{\"transaction_id\": <id>, \"field\": \"<field>\", "
    "\"correct_value\": <value>, \"reason\": \"...\"}}] or [] if all correct.\n"
    "No other text."
)


class EnrichmentAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model=getattr(settings, 'AI_MODEL_CLASSIFICATION', 'claude-sonnet-4-5-20250929'),
        )
        self.verifier_model = getattr(settings, 'AI_MODEL_VERIFIER', 'claude-haiku-4-5-20251001')

    def execute(self, user, context: dict) -> AgentResult:
        # Get unclassified transactions (no pcg_code yet)
        unclassified = UnifiedTransaction.objects.filter(
            user=user, pcg_code='', direction='outflow',
        ).exclude(category='transfer')

        if not unclassified.exists():
            return AgentResult(success=True, items_processed=0)

        batch_size = 20
        total_classified = 0
        all_classifications = []
        handlers = make_tool_handlers(user)

        # Process in batches
        for i in range(0, unclassified.count(), batch_size):
            batch = list(unclassified[i:i + batch_size])
            batch_data = [
                {
                    'id': tx.id,
                    'vendor_name': tx.vendor_name,
                    'amount': str(tx.amount) if tx.amount else '?',
                    'currency': tx.currency,
                    'description': tx.description[:100],
                    'source_type': tx.source_type,
                    'category': tx.category,
                }
                for tx in batch
            ]

            user_msg = (
                f"Classify these {len(batch)} transactions. "
                f"For each: 1) think, 2) classify_expense.\n\n"
                f"Transactions:\n{json.dumps(batch_data, ensure_ascii=False)}"
            )

            tools = [THINK_TOOL, CLASSIFY_EXPENSE_TOOL]

            try:
                messages, stats = self._run_agentic_loop(
                    system=ENRICHMENT_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': user_msg}],
                    tools=tools,
                    tool_handlers=handlers,
                    max_iterations=len(batch) + 5,
                )
                total_classified += len(batch)
                all_classifications.extend(batch_data)
            except Exception as e:
                logger.error(f'[Enrichment] Batch error: {e}')

        # Run verifier on all classifications
        corrections = self.run_verifier(user, all_classifications, context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=total_classified,
            stats={'classifications': total_classified, 'corrections': len(corrections)},
        )

    def run_verifier(self, user, classifications: list, context: dict) -> list:
        if not classifications:
            return []

        # Re-read the classified transactions for verification
        tx_ids = [c['id'] for c in classifications]
        txs = UnifiedTransaction.objects.filter(user=user, id__in=tx_ids)
        verifier_data = [
            {
                'id': tx.id,
                'vendor_name': tx.vendor_name,
                'amount': str(tx.amount),
                'pcg_code': tx.pcg_code,
                'pcg_label': tx.pcg_label,
                'category': tx.category,
                'business_personal': tx.business_personal,
                'tva_deductible': tx.tva_deductible,
            }
            for tx in txs
        ]

        prompt = ENRICHMENT_VERIFIER_PROMPT.format(
            classifications=json.dumps(verifier_data, ensure_ascii=False)
        )

        try:
            response = self._call_llm_sync(
                system='You are an accounting verification assistant.',
                messages=[{'role': 'user', 'content': prompt}],
                model=self.verifier_model,
            )
            text = self._extract_text(response)
            corrections = self._extract_json(text)
            if isinstance(corrections, list):
                return corrections
        except Exception as e:
            logger.warning(f'[Enrichment-Verifier] Error: {e}')

        return []

    def _apply_corrections(self, user, corrections):
        for correction in corrections:
            tx_id = correction.get('transaction_id')
            field = correction.get('field')
            value = correction.get('correct_value')
            if tx_id and field and value is not None:
                try:
                    tx = UnifiedTransaction.objects.get(id=tx_id, user=user)
                    if hasattr(tx, field):
                        setattr(tx, field, value)
                        tx.save()
                        logger.info(f'[Enrichment-Verifier] Corrected TX #{tx_id}: {field}={value}')
                except UnifiedTransaction.DoesNotExist:
                    pass
```

- [ ] **Step 4: Implement CorrelationAgent (Sonnet worker, Sonnet verifier)**

```python
# ai_agent/services/agents/correlation.py
"""
Correlation Agent — the core of the pipeline.

Groups UnifiedTransactions into TransactionClusters.
Any source can match any other source (no email-hub limitation).

Worker: Sonnet (complex multi-source reasoning)
Verifier: Sonnet (complex correlation audit)
"""
import json
import logging

from django.conf import settings
from django.db.models import Count

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.normalization import normalize_vendor
from ai_agent.services.tools import (
    THINK_TOOL, SEARCH_TRANSACTIONS_TOOL, CREATE_CLUSTER_TOOL,
    ADD_TO_CLUSTER_TOOL, FLAG_CONTRADICTION_TOOL,
    make_tool_handlers,
)

logger = logging.getLogger(__name__)

CORRELATION_SYSTEM_PROMPT = (
    "You are a financial data correlation expert. Your job is to group related "
    "transactions from DIFFERENT sources into clusters representing the SAME "
    "business operation.\n\n"
    "SOURCES: stripe (payment processor revenue), mollie (payment processor), "
    "paypal (payments), bank_api (bank debits/credits), bank_import (uploaded bank statements), "
    "email (invoices, receipts, shipping notifications).\n\n"
    "WORKFLOW for each vendor group:\n"
    "1. ALWAYS call 'think' first to analyze the transactions and plan your approach.\n"
    "2. Call 'search_transactions' to find related transactions across sources.\n"
    "3. Group related transactions into clusters using 'create_cluster'.\n"
    "4. Add confirmations/enrichments to existing clusters with 'add_to_cluster'.\n"
    "5. Flag contradictions with 'flag_contradiction'.\n\n"
    "CORRELATION RULES:\n"
    "- Same reference (invoice/order number) across sources → SAME cluster\n"
    "- Same vendor + same amount + date within 5 days → likely SAME cluster\n"
    "- Stripe charge + bank credit of same amount + 2-3 day lag → SAME (payout settlement)\n"
    "- Email invoice + bank debit of same amount/vendor → SAME cluster\n"
    "- Shipping email (no amount) + order email from same vendor → SAME cluster\n"
    "- Provider fee (Stripe fee, PayPal fee) → separate cluster type='fee'\n\n"
    "DO NOT CLUSTER:\n"
    "- Different amounts on different dates from same vendor = different transactions\n"
    "- Different order/invoice numbers = different transactions, PERIOD\n"
    "- Recurring subscriptions: each month is a SEPARATE cluster\n\n"
    "EVIDENCE ROLES when adding to clusters:\n"
    "- 'confirmation': same data from different source (increases confidence)\n"
    "- 'enrichment': adds missing info (items, tax details, tracking number)\n"
    "- 'contradiction': conflicts with existing data (different amount, etc.)\n\n"
    "Process ALL transactions. Be thorough but precise."
)

CORRELATION_VERIFIER_PROMPT = (
    "Review these transaction clusters. ONLY flag CLEAR errors:\n"
    "- Transactions with different order numbers merged together\n"
    "- Transactions with very different amounts in the same cluster\n"
    "- Transactions from completely unrelated vendors in the same cluster\n"
    "- Monthly subscriptions merged into one cluster (should be separate)\n\n"
    "Be CONSERVATIVE. Only reject if 100% certain the cluster is wrong.\n\n"
    "Clusters:\n{clusters}\n\n"
    "Return: [{{\"cluster_id\": <id>, \"action\": \"split\"|\"reject\", "
    "\"reason\": \"...\", \"transaction_ids_to_remove\": [<ids>]}}] or [] if all correct.\n"
    "No other text."
)


class CorrelationAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model=getattr(settings, 'AI_MODEL_CORRELATION', 'claude-sonnet-4-5-20250929'),
        )
        self.verifier_model = getattr(settings, 'AI_MODEL_CORRELATION', 'claude-sonnet-4-5-20250929')

    def execute(self, user, context: dict) -> AgentResult:
        # Get unclustered transactions
        unclustered = UnifiedTransaction.objects.filter(user=user, cluster__isnull=True)

        if not unclustered.exists():
            return AgentResult(success=True, items_processed=0)

        handlers = make_tool_handlers(user)
        tools = [
            THINK_TOOL, SEARCH_TRANSACTIONS_TOOL, CREATE_CLUSTER_TOOL,
            ADD_TO_CLUSTER_TOOL, FLAG_CONTRADICTION_TOOL,
        ]

        # Group by normalized vendor name for efficient processing
        vendor_groups = {}
        for tx in unclustered:
            key = tx.vendor_name_normalized or 'unknown'
            vendor_groups.setdefault(key, []).append(tx)

        clusters_created = 0
        total_processed = 0

        # Process vendor groups in batches
        batch_vendors = []
        batch_txs = []

        for vendor, txs in vendor_groups.items():
            batch_vendors.append(vendor)
            batch_txs.extend(txs)

            # Process when batch is big enough or last vendor
            if len(batch_txs) >= 30 or vendor == list(vendor_groups.keys())[-1]:
                batch_data = [
                    {
                        'id': tx.id,
                        'source_type': tx.source_type,
                        'direction': tx.direction,
                        'vendor_name': tx.vendor_name,
                        'vendor_normalized': tx.vendor_name_normalized,
                        'amount': str(tx.amount) if tx.amount else None,
                        'currency': tx.currency,
                        'transaction_date': str(tx.transaction_date) if tx.transaction_date else None,
                        'reference': tx.reference,
                        'description': tx.description[:80],
                        'category': tx.category,
                    }
                    for tx in batch_txs
                ]

                user_msg = (
                    f"Correlate these {len(batch_data)} unclustered transactions "
                    f"from vendors: {', '.join(batch_vendors)}.\n"
                    f"Also search for existing clustered transactions that these might match.\n\n"
                    f"Transactions:\n{json.dumps(batch_data, ensure_ascii=False)}"
                )

                try:
                    messages, stats = self._run_agentic_loop(
                        system=CORRELATION_SYSTEM_PROMPT,
                        messages=[{'role': 'user', 'content': user_msg}],
                        tools=tools,
                        tool_handlers=handlers,
                        max_iterations=len(batch_txs) + 10,
                    )
                    total_processed += len(batch_txs)
                except Exception as e:
                    logger.error(f'[Correlation] Batch error: {e}')

                batch_vendors = []
                batch_txs = []

        # Count clusters created
        clusters_created = TransactionCluster.objects.filter(
            user=user, created_by='ai_agent'
        ).count()

        # Run verifier
        corrections = self.run_verifier(user, [], context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=total_processed,
            stats={
                'clusters_created': clusters_created,
                'corrections': len(corrections),
            },
        )

    def run_verifier(self, user, results: list, context: dict) -> list:
        recent_clusters = TransactionCluster.objects.filter(
            user=user, verification_status='auto',
        ).prefetch_related('transactions')[:50]

        if not recent_clusters:
            return []

        clusters_data = []
        for cluster in recent_clusters:
            txs = cluster.transactions.all()
            clusters_data.append({
                'cluster_id': cluster.id,
                'label': cluster.label,
                'type': cluster.cluster_type,
                'confidence': cluster.confidence,
                'margin': str(cluster.margin),
                'transactions': [
                    {
                        'id': tx.id,
                        'source': tx.source_type,
                        'vendor': tx.vendor_name,
                        'amount': str(tx.amount),
                        'date': str(tx.transaction_date),
                        'reference': tx.reference,
                        'evidence_role': tx.evidence_role,
                    }
                    for tx in txs
                ],
            })

        prompt = CORRELATION_VERIFIER_PROMPT.format(
            clusters=json.dumps(clusters_data, ensure_ascii=False)
        )

        try:
            response = self._call_llm_sync(
                system='You are a financial data correlation auditor.',
                messages=[{'role': 'user', 'content': prompt}],
                model=self.verifier_model,
            )
            text = self._extract_text(response)
            corrections = self._extract_json(text)
            if isinstance(corrections, list):
                return corrections
        except Exception as e:
            logger.warning(f'[Correlation-Verifier] Error: {e}')

        return []

    def _apply_corrections(self, user, corrections):
        for correction in corrections:
            cluster_id = correction.get('cluster_id')
            action = correction.get('action')
            tx_ids = correction.get('transaction_ids_to_remove', [])

            if action == 'reject' and cluster_id:
                try:
                    cluster = TransactionCluster.objects.get(id=cluster_id, user=user)
                    cluster.transactions.all().update(cluster=None)
                    cluster.delete()
                    logger.info(f'[Correlation-Verifier] Rejected cluster #{cluster_id}')
                except TransactionCluster.DoesNotExist:
                    pass

            elif action == 'split' and tx_ids:
                UnifiedTransaction.objects.filter(
                    user=user, id__in=tx_ids
                ).update(cluster=None)
                if cluster_id:
                    try:
                        cluster = TransactionCluster.objects.get(id=cluster_id, user=user)
                        cluster.recalculate_metrics()
                    except TransactionCluster.DoesNotExist:
                        pass
                logger.info(
                    f'[Correlation-Verifier] Split TX {tx_ids} from cluster #{cluster_id}'
                )
```

- [ ] **Step 5: Implement ComputationAgent (no LLM)**

```python
# ai_agent/services/agents/computation.py
"""
Computation Agent — pure Python, no LLM.

Recalculates all cluster metrics: revenue, costs, margin, tax totals.
Also computes derivable tax fields on transactions.
"""
import logging
from decimal import Decimal, InvalidOperation

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class ComputationAgent(BaseAgent):
    """No LLM — pure deterministic computation."""

    def execute(self, user, context: dict) -> AgentResult:
        stats = {'clusters_updated': 0, 'tax_computed': 0}

        # 1. Compute derivable tax fields on transactions
        txs = UnifiedTransaction.objects.filter(user=user, amount__isnull=False)

        for tx in txs:
            updated = False

            if tx.amount and tx.tax_amount and not tx.amount_tax_excl:
                tx.amount_tax_excl = tx.amount - tx.tax_amount
                updated = True

            if tx.amount and tx.tax_rate and not tx.tax_amount:
                try:
                    rate = tx.tax_rate
                    tx.tax_amount = (tx.amount * rate / (Decimal('100') + rate)).quantize(Decimal('0.01'))
                    tx.amount_tax_excl = (tx.amount - tx.tax_amount).quantize(Decimal('0.01'))
                    updated = True
                except (InvalidOperation, ZeroDivisionError):
                    pass

            if tx.amount_tax_excl and tx.tax_amount and not tx.amount:
                tx.amount = tx.amount_tax_excl + tx.tax_amount
                updated = True

            if updated:
                tx.save()
                stats['tax_computed'] += 1

        # 2. Recalculate all cluster metrics
        clusters = TransactionCluster.objects.filter(user=user)
        for cluster in clusters:
            cluster.recalculate_metrics()
            stats['clusters_updated'] += 1

        logger.info(f'[Computation] Done: {stats}')
        return AgentResult(success=True, items_processed=stats['clusters_updated'], stats=stats)
```

- [ ] **Step 6: Implement VerificationAgent (Haiku for simple, Sonnet for complex)**

```python
# ai_agent/services/agents/verification.py
"""
Verification Agent — audits clusters with low confidence or contradictions.

Uses Haiku for simple checks, Sonnet for complex anomalies.
Fresh context — no self-confirmation (rapport §3.2).
"""
import json
import logging

from django.conf import settings

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

VERIFICATION_SYSTEM_PROMPT = (
    "You are a financial data auditor. Review these transaction clusters "
    "for anomalies and quality issues.\n\n"
    "CHECK FOR:\n"
    "1. Amount mismatches: bank debit ≠ invoice amount in same cluster\n"
    "2. Date outliers: transactions > 14 days apart in same cluster\n"
    "3. Currency mismatches: different currencies without conversion explanation\n"
    "4. Missing data: cluster marked complete but missing key fields\n"
    "5. Suspicious margins: negative margin on a sale, or margin > 90%\n"
    "6. Tax inconsistencies: amount_tax_excl + tax_amount ≠ amount\n\n"
    "For each issue found, return:\n"
    "{\"cluster_id\": <id>, \"severity\": \"critical\"|\"warning\"|\"info\", "
    "\"issue\": \"description\", \"suggestion\": \"what to fix\"}\n\n"
    "Return JSON array. Empty array if no issues."
)


class VerificationAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model=getattr(settings, 'AI_MODEL_VERIFIER', 'claude-haiku-4-5-20251001'),
        )
        self.sonnet_model = getattr(settings, 'AI_MODEL_CLASSIFICATION', 'claude-sonnet-4-5-20250929')

    def execute(self, user, context: dict) -> AgentResult:
        anomalies = []

        # 1. Quick deterministic checks (no LLM)
        anomalies.extend(self._check_tax_consistency(user))
        anomalies.extend(self._check_date_outliers(user))

        # 2. LLM audit of low-confidence clusters
        low_confidence = TransactionCluster.objects.filter(
            user=user, confidence__lt=0.8, verification_status='auto',
        ).prefetch_related('transactions')[:20]

        if low_confidence:
            llm_anomalies = self._llm_audit(low_confidence)
            anomalies.extend(llm_anomalies)

        # 3. LLM audit of contradictions (use Sonnet — complex)
        contradictions = UnifiedTransaction.objects.filter(
            user=user, evidence_role='contradiction',
        )
        if contradictions.exists():
            contradiction_anomalies = self._audit_contradictions(user, contradictions)
            anomalies.extend(contradiction_anomalies)

        logger.info(f'[Verification] Found {len(anomalies)} anomalies')
        return AgentResult(
            success=True,
            items_processed=len(anomalies),
            stats={
                'anomalies_total': len(anomalies),
                'critical': sum(1 for a in anomalies if a.get('severity') == 'critical'),
                'warnings': sum(1 for a in anomalies if a.get('severity') == 'warning'),
            },
        )

    def _check_tax_consistency(self, user) -> list:
        """Deterministic: check amount = amount_tax_excl + tax_amount."""
        anomalies = []
        txs = UnifiedTransaction.objects.filter(
            user=user,
            amount__isnull=False,
            amount_tax_excl__isnull=False,
            tax_amount__isnull=False,
        )
        for tx in txs:
            expected = tx.amount_tax_excl + tx.tax_amount
            diff = abs(tx.amount - expected)
            if diff > Decimal('0.02'):
                anomalies.append({
                    'transaction_id': tx.id,
                    'severity': 'warning',
                    'issue': f'Tax inconsistency: {tx.amount} ≠ {tx.amount_tax_excl} + {tx.tax_amount} (diff={diff})',
                    'suggestion': 'Recompute tax fields or flag for manual review.',
                })
        return anomalies

    def _check_date_outliers(self, user) -> list:
        """Deterministic: check for clusters with transactions > 14 days apart."""
        from django.db.models import Max, Min
        anomalies = []
        clusters = TransactionCluster.objects.filter(user=user).annotate(
            min_date=Min('transactions__transaction_date'),
            max_date=Max('transactions__transaction_date'),
        )
        for cluster in clusters:
            if cluster.min_date and cluster.max_date:
                span = (cluster.max_date - cluster.min_date).days
                if span > 14:
                    anomalies.append({
                        'cluster_id': cluster.id,
                        'severity': 'warning',
                        'issue': f'Date span {span} days in cluster "{cluster.label}"',
                        'suggestion': 'Check if all transactions belong together.',
                    })
        return anomalies

    def _llm_audit(self, clusters) -> list:
        clusters_data = []
        for cluster in clusters:
            txs = cluster.transactions.all()
            clusters_data.append({
                'cluster_id': cluster.id,
                'label': cluster.label,
                'type': cluster.cluster_type,
                'margin': str(cluster.margin),
                'confidence': cluster.confidence,
                'corroboration_score': cluster.corroboration_score,
                'transactions': [
                    {
                        'id': tx.id, 'source': tx.source_type,
                        'vendor': tx.vendor_name, 'amount': str(tx.amount),
                        'currency': tx.currency,
                        'date': str(tx.transaction_date),
                    }
                    for tx in txs
                ],
            })

        try:
            response = self._call_llm_sync(
                system=VERIFICATION_SYSTEM_PROMPT,
                messages=[{
                    'role': 'user',
                    'content': json.dumps(clusters_data, ensure_ascii=False),
                }],
            )
            text = self._extract_text(response)
            result = self._extract_json(text)
            if isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f'[Verification] LLM audit error: {e}')

        return []

    def _audit_contradictions(self, user, contradictions) -> list:
        data = [
            {
                'id': tx.id, 'vendor': tx.vendor_name, 'amount': str(tx.amount),
                'source': tx.source_type, 'cluster_id': tx.cluster_id,
                'description': tx.description[:100],
            }
            for tx in contradictions[:20]
        ]

        try:
            response = self._call_llm_sync(
                system=(
                    "Review these flagged contradictions. For each, determine:\n"
                    "1. Which data source is more trustworthy?\n"
                    "2. What action should be taken?\n"
                    "Return: [{\"id\": <tx_id>, \"severity\": \"critical\"|\"warning\", "
                    "\"issue\": \"...\", \"suggestion\": \"...\"}]"
                ),
                messages=[{'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                model=self.sonnet_model,
            )
            text = self._extract_text(response)
            result = self._extract_json(text)
            if isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f'[Verification] Contradiction audit error: {e}')

        return []
```

- [ ] **Step 7: Commit**

```bash
git add ai_agent/services/agents/ ai_agent/services/tools.py
git commit -m "feat: add specialized agents (Ingestion, Enrichment, Correlation, Computation, Verification)"
```

---

## Task 6: Pipeline Orchestrator — State Machine

**Files:**
- Create: `ai_agent/services/orchestrator.py`
- Modify: `ai_agent/views.py`
- Modify: `ai_agent/models.py` (update PipelineRun status choices)

- [ ] **Step 1: Implement the orchestrator**

```python
# ai_agent/services/orchestrator.py
"""
Pipeline Orchestrator — state machine with recovery paths.

Inspired by Claude Code architecture (rapport §2.1):
- Phases execute sequentially: INGESTION → ENRICHMENT → CORRELATION → COMPUTATION → VERIFICATION
- Each phase has a specialized agent with Worker/Verifier/Cleaner
- Recovery paths: rate limit, token overflow, tool error, circuit breaker, phase timeout
- Progress events streamed to frontend via PipelineRun.state

Usage:
    result = run_unified_pipeline(user)
"""
import logging
import time

from django.utils import timezone

from ai_agent.models import PipelineRun
from ai_agent.services.agents.ingestion import IngestionAgent
from ai_agent.services.agents.enrichment import EnrichmentAgent
from ai_agent.services.agents.correlation import CorrelationAgent
from ai_agent.services.agents.computation import ComputationAgent
from ai_agent.services.agents.verification import VerificationAgent

logger = logging.getLogger(__name__)

PHASE_TIMEOUT_SECONDS = 600  # 10 minutes per phase


class PipelineOrchestrator:
    """
    Orchestrates the 5-phase pipeline with progress tracking.
    Each phase runs its specialized agent.
    """

    PHASES = [
        ('ingestion', IngestionAgent, 'Ingesting data from all sources'),
        ('enrichment', EnrichmentAgent, 'Classifying expenses and enriching data'),
        ('correlation', CorrelationAgent, 'Correlating transactions across sources'),
        ('computation', ComputationAgent, 'Computing metrics and tax fields'),
        ('verification', VerificationAgent, 'Auditing clusters and detecting anomalies'),
    ]

    def run(self, user, pipeline_run: PipelineRun | None = None) -> dict:
        """Execute the full pipeline. Returns stats dict."""

        if not pipeline_run:
            pipeline_run = PipelineRun.objects.create(user=user, status='pending')

        all_stats = {}
        phase_timings = {}

        for phase_name, agent_class, description in self.PHASES:
            logger.info(f'[Pipeline] === {phase_name.upper()} === {description}')

            # Update pipeline run status
            pipeline_run.status = phase_name
            pipeline_run.state = {
                **pipeline_run.state,
                'current_phase': phase_name,
                'phase_description': description,
            }
            pipeline_run.save()

            phase_start = time.time()

            try:
                agent = agent_class()
                result = agent.execute(user, context={'pipeline_run': pipeline_run})

                phase_duration = time.time() - phase_start
                phase_timings[phase_name] = round(phase_duration, 2)

                all_stats[phase_name] = {
                    'success': result.success,
                    'items_processed': result.items_processed,
                    'duration_seconds': phase_timings[phase_name],
                    **result.stats,
                }

                if result.errors:
                    all_stats[phase_name]['errors'] = result.errors

                logger.info(
                    f'[Pipeline] {phase_name} completed: '
                    f'{result.items_processed} items in {phase_timings[phase_name]}s'
                )

                # Update pipeline state with phase results
                pipeline_run.state = {
                    **pipeline_run.state,
                    f'{phase_name}_stats': all_stats[phase_name],
                }
                pipeline_run.save()

            except Exception as e:
                phase_duration = time.time() - phase_start
                logger.error(f'[Pipeline] {phase_name} FAILED after {phase_duration:.1f}s: {e}')

                all_stats[phase_name] = {
                    'success': False,
                    'error': str(e),
                    'duration_seconds': round(phase_duration, 2),
                }

                # Continue to next phase (don't abort entire pipeline)
                pipeline_run.state = {
                    **pipeline_run.state,
                    f'{phase_name}_stats': all_stats[phase_name],
                }
                pipeline_run.save()
                continue

        # Pipeline complete
        pipeline_run.status = 'complete'
        pipeline_run.completed_at = timezone.now()
        pipeline_run.stats = all_stats
        pipeline_run.state = {
            **pipeline_run.state,
            'current_phase': 'complete',
            'phase_timings': phase_timings,
        }
        pipeline_run.save()

        logger.info(f'[Pipeline] === COMPLETE === Stats: {all_stats}')
        return all_stats


def run_unified_pipeline(user) -> dict:
    """Entry point — creates a PipelineRun and runs the full pipeline."""
    pipeline_run = PipelineRun.objects.create(user=user, status='pending')

    try:
        orchestrator = PipelineOrchestrator()
        stats = orchestrator.run(user, pipeline_run)
        return {
            'pipeline_run_id': pipeline_run.id,
            'status': 'complete',
            'stats': stats,
        }
    except Exception as e:
        pipeline_run.status = 'failed'
        pipeline_run.error_message = str(e)
        pipeline_run.completed_at = timezone.now()
        pipeline_run.save()
        return {
            'pipeline_run_id': pipeline_run.id,
            'status': 'failed',
            'error': str(e),
        }
```

- [ ] **Step 2: Add the new pipeline view**

```python
# In ai_agent/views.py — ADD this new view after existing views

class UnifiedPipelineView(APIView):
    """POST /api/ai/unified-pipeline/ — run the new unified pipeline."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ai_agent.services.orchestrator import run_unified_pipeline
        result = run_unified_pipeline(request.user)
        return Response(result)
```

- [ ] **Step 3: Update ai_agent/urls.py**

```python
# ai_agent/urls.py — ADD new URL
urlpatterns = [
    path('classify/', views.AIClassifyView.as_view(), name='ai-classify'),
    path('correlate/', views.AICorrelateView.as_view(), name='ai-correlate'),
    path('classify-batch/', views.classify_batch_view, name='classify-batch'),
    path('classify-batch/<int:run_id>/', views.classify_batch_status_view, name='classify-batch-status'),
    path('unified-pipeline/', views.UnifiedPipelineView.as_view(), name='unified-pipeline'),
]
```

- [ ] **Step 4: Commit**

```bash
git add ai_agent/services/orchestrator.py ai_agent/views.py ai_agent/urls.py
git commit -m "feat: add pipeline orchestrator with 5-phase state machine"
```

---

## Task 7: Bank File Import — CSV Parser

**Files:**
- Create: `ai_agent/services/parsers/__init__.py`
- Create: `ai_agent/services/parsers/csv_parser.py`
- Create: `ai_agent/services/normalizers/bank_import.py`
- Create: `ai_agent/tests/test_parsers.py`

- [ ] **Step 1: Write failing tests**

```python
# ai_agent/tests/test_parsers.py
from datetime import date
from decimal import Decimal

from django.test import TestCase

from ai_agent.services.parsers.csv_parser import CSVBankParser, ParseResult


class CSVBankParserTest(TestCase):

    def test_parse_bnp_format(self):
        content = (
            '"Date opération";"Libellé";"Débit";"Crédit"\n'
            '"15/03/2026";"CB AMAZON PARIS 02";"-49.99";""\n'
            '"16/03/2026";"VIR STRIPE PAYOUT";"";"+500.00"\n'
        ).encode('latin-1')

        parser = CSVBankParser()
        result = parser.parse(content, filename='export_bnp.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)

        tx1 = result.transactions[0]
        self.assertEqual(tx1.date, date(2026, 3, 15))
        self.assertEqual(tx1.amount, Decimal('-49.99'))
        self.assertEqual(tx1.label, 'CB AMAZON PARIS 02')

        tx2 = result.transactions[1]
        self.assertEqual(tx2.amount, Decimal('500.00'))

    def test_parse_revolut_format(self):
        content = (
            'Type,Started Date,Completed Date,Description,Amount,Currency\n'
            'CARD_PAYMENT,2026-03-15 10:00:00,2026-03-15 10:00:00,Amazon,-25.00,EUR\n'
            'TOPUP,2026-03-16 12:00:00,2026-03-16 12:00:00,Top-up,100.00,EUR\n'
        ).encode('utf-8')

        parser = CSVBankParser()
        result = parser.parse(content, filename='revolut.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)
        self.assertEqual(result.transactions[0].amount, Decimal('-25.00'))
        self.assertEqual(result.transactions[0].currency, 'EUR')

    def test_parse_generic_csv(self):
        content = (
            'Date;Description;Montant\n'
            '15/03/2026;Achat Amazon;-35.50\n'
            '16/03/2026;Salaire;+2500.00\n'
        ).encode('utf-8')

        parser = CSVBankParser()
        result = parser.parse(content, filename='banque.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)

    def test_detect_encoding(self):
        parser = CSVBankParser()
        # Latin-1 with accented chars
        content = '"Libellé";"Crédit"'.encode('latin-1')
        encoding = parser._detect_encoding(content)
        self.assertIn(encoding.lower(), ['latin-1', 'iso-8859-1', 'windows-1252', 'latin1'])

    def test_empty_file(self):
        parser = CSVBankParser()
        result = parser.parse(b'', filename='empty.csv')
        self.assertIsNone(result)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python manage.py test ai_agent.tests.test_parsers -v 2`
Expected: ImportError

- [ ] **Step 3: Implement CSVBankParser**

```python
# ai_agent/services/parsers/__init__.py
from .csv_parser import CSVBankParser

__all__ = ['CSVBankParser']
```

```python
# ai_agent/services/parsers/csv_parser.py
"""
CSV Bank Statement Parser — multi-bank support.

Strategy:
1. Detect encoding + separator
2. Match known bank signatures (headers)
3. Heuristic column mapping for unknown banks
4. LLM fallback (not implemented here — handled by orchestrator)
"""
import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass
class RawBankRow:
    date: date
    label: str
    amount: Decimal
    currency: str = 'EUR'
    value_date: date | None = None
    reference: str = ''
    raw_data: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    transactions: list[RawBankRow]
    bank_name: str | None = None
    account_id: str | None = None
    date_range: tuple[date, date] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ColumnMapping:
    date_col: int | None = None
    value_date_col: int | None = None
    label_col: int | None = None
    amount_col: int | None = None
    debit_col: int | None = None
    credit_col: int | None = None
    currency_col: int | None = None
    reference_col: int | None = None
    date_format: str = '%d/%m/%Y'
    confidence: float = 0.0

    def compute_confidence(self) -> float:
        score = 0.0
        if self.date_col is not None:
            score += 0.3
        if self.amount_col is not None or (self.debit_col is not None and self.credit_col is not None):
            score += 0.4
        if self.label_col is not None:
            score += 0.3
        self.confidence = score
        return score


# Known bank CSV signatures
KNOWN_SIGNATURES = {
    'bnp': {
        'headers_match': lambda h: any('opération' in x or 'operation' in x for x in h) and any('libellé' in x or 'libelle' in x for x in h),
        'date_format': '%d/%m/%Y',
        'encoding': 'latin-1',
        'separator': ';',
        'build_mapping': lambda h: _build_bnp_mapping(h),
    },
    'revolut': {
        'headers_match': lambda h: 'started date' in h and 'description' in h and 'amount' in h,
        'date_format': '%Y-%m-%d %H:%M:%S',
        'encoding': 'utf-8',
        'separator': ',',
        'build_mapping': lambda h: _build_revolut_mapping(h),
    },
    'n26': {
        'headers_match': lambda h: 'payee' in h and 'transaction type' in h,
        'date_format': '%Y-%m-%d',
        'encoding': 'utf-8',
        'separator': ',',
        'build_mapping': lambda h: _build_n26_mapping(h),
    },
}


def _build_bnp_mapping(headers):
    m = ColumnMapping(date_format='%d/%m/%Y')
    for i, h in enumerate(headers):
        if 'opération' in h or 'operation' in h:
            m.date_col = i
        elif 'libellé' in h or 'libelle' in h:
            m.label_col = i
        elif 'débit' in h or 'debit' in h:
            m.debit_col = i
        elif 'crédit' in h or 'credit' in h:
            m.credit_col = i
        elif 'montant' in h:
            m.amount_col = i
    m.compute_confidence()
    return m


def _build_revolut_mapping(headers):
    m = ColumnMapping(date_format='%Y-%m-%d %H:%M:%S')
    for i, h in enumerate(headers):
        if h == 'started date':
            m.date_col = i
        elif h == 'completed date':
            m.value_date_col = i
        elif h == 'description':
            m.label_col = i
        elif h == 'amount':
            m.amount_col = i
        elif h == 'currency':
            m.currency_col = i
    m.compute_confidence()
    return m


def _build_n26_mapping(headers):
    m = ColumnMapping(date_format='%Y-%m-%d')
    for i, h in enumerate(headers):
        if h == 'date':
            m.date_col = i
        elif h == 'payee':
            m.label_col = i
        elif 'amount' in h:
            m.amount_col = i
    m.compute_confidence()
    return m


# Heuristic column detection patterns
_DATE_PATTERNS = ['date', 'datum', 'fecha', 'data', 'booking', 'opération', 'operation']
_AMOUNT_PATTERNS = ['amount', 'montant', 'betrag', 'importe', 'somme', 'total']
_DEBIT_PATTERNS = ['débit', 'debit', 'soll', 'charge', 'sortie']
_CREDIT_PATTERNS = ['crédit', 'credit', 'haben', 'deposit', 'entrée', 'entree']
_LABEL_PATTERNS = ['libellé', 'libelle', 'label', 'description', 'wording', 'payee',
                   'beneficiary', 'text', 'verwendungszweck', 'concepto', 'communication']
_CURRENCY_PATTERNS = ['currency', 'devise', 'währung', 'divisa', 'monnaie']
_DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y', '%m/%d/%Y',
                 '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']


class CSVBankParser:

    def parse(self, file_content: bytes, filename: str | None = None) -> ParseResult | None:
        if not file_content or not file_content.strip():
            return None

        encoding = self._detect_encoding(file_content)
        text = file_content.decode(encoding, errors='replace')

        separator = self._detect_separator(text)
        headers = self._read_headers(text, separator)

        if not headers:
            return None

        normalized_headers = [h.lower().strip() for h in headers]

        # Try known bank signatures
        for bank_name, sig in KNOWN_SIGNATURES.items():
            if sig['headers_match'](normalized_headers):
                mapping = sig['build_mapping'](normalized_headers)
                return self._parse_with_mapping(
                    text, mapping, separator, bank_name=bank_name,
                )

        # Heuristic mapping
        mapping = self._infer_column_mapping(normalized_headers)
        if mapping.confidence >= 0.7:
            return self._parse_with_mapping(text, mapping, separator)

        # Try with different date formats
        for fmt in _DATE_FORMATS:
            mapping.date_format = fmt
            result = self._parse_with_mapping(text, mapping, separator)
            if result and result.transactions:
                return result

        return None

    def _detect_encoding(self, content: bytes) -> str:
        try:
            import chardet
            result = chardet.detect(content[:10000])
            if result and result.get('encoding'):
                return result['encoding']
        except ImportError:
            pass

        # Fallback: try utf-8, then latin-1
        try:
            content.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            return 'latin-1'

    def _detect_separator(self, text: str) -> str:
        first_line = text.split('\n')[0] if text else ''
        semicolons = first_line.count(';')
        commas = first_line.count(',')
        tabs = first_line.count('\t')

        if semicolons > commas and semicolons > tabs:
            return ';'
        if tabs > commas:
            return '\t'
        return ','

    def _read_headers(self, text: str, separator: str) -> list[str]:
        reader = csv.reader(io.StringIO(text), delimiter=separator)
        try:
            headers = next(reader)
            return [h.strip().strip('"') for h in headers]
        except StopIteration:
            return []

    def _infer_column_mapping(self, headers: list[str]) -> ColumnMapping:
        mapping = ColumnMapping()

        for i, h in enumerate(headers):
            if any(p in h for p in _DEBIT_PATTERNS) and mapping.debit_col is None:
                mapping.debit_col = i
            elif any(p in h for p in _CREDIT_PATTERNS) and mapping.credit_col is None:
                mapping.credit_col = i
            elif any(p in h for p in _AMOUNT_PATTERNS) and mapping.amount_col is None:
                mapping.amount_col = i
            elif any(p in h for p in _LABEL_PATTERNS) and mapping.label_col is None:
                mapping.label_col = i
            elif any(p in h for p in _CURRENCY_PATTERNS) and mapping.currency_col is None:
                mapping.currency_col = i
            elif any(p in h for p in _DATE_PATTERNS):
                if mapping.date_col is None:
                    mapping.date_col = i
                elif 'valeur' in h or 'value' in h:
                    mapping.value_date_col = i

        mapping.compute_confidence()
        return mapping

    def _parse_with_mapping(self, text: str, mapping: ColumnMapping,
                            separator: str, bank_name: str | None = None) -> ParseResult:
        reader = csv.reader(io.StringIO(text), delimiter=separator)
        next(reader, None)  # skip header

        transactions = []
        warnings = []
        dates = []

        for row_num, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue

            try:
                # Parse date
                tx_date = self._parse_date(
                    self._get_cell(row, mapping.date_col), mapping.date_format
                )
                if not tx_date:
                    warnings.append(f'Row {row_num}: could not parse date')
                    continue

                # Parse amount
                amount = self._parse_amount(row, mapping)
                if amount is None:
                    warnings.append(f'Row {row_num}: could not parse amount')
                    continue

                # Parse label
                label = self._get_cell(row, mapping.label_col) or f'Row {row_num}'

                # Parse currency
                currency = self._get_cell(row, mapping.currency_col) or 'EUR'

                # Parse value date
                value_date = self._parse_date(
                    self._get_cell(row, mapping.value_date_col), mapping.date_format
                )

                raw = {str(i): cell for i, cell in enumerate(row)}

                transactions.append(RawBankRow(
                    date=tx_date,
                    label=label.strip(),
                    amount=amount,
                    currency=currency.upper(),
                    value_date=value_date,
                    raw_data=raw,
                ))
                dates.append(tx_date)

            except Exception as e:
                warnings.append(f'Row {row_num}: {e}')

        date_range = (min(dates), max(dates)) if dates else None

        return ParseResult(
            transactions=transactions,
            bank_name=bank_name,
            date_range=date_range,
            warnings=warnings,
        )

    def _get_cell(self, row: list, col: int | None) -> str:
        if col is None or col >= len(row):
            return ''
        return row[col].strip().strip('"')

    def _parse_date(self, value: str, fmt: str) -> date | None:
        if not value:
            return None
        value = value.strip().strip('"')
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            # Try common fallbacks
            for fallback_fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(value, fallback_fmt).date()
                except ValueError:
                    continue
        return None

    def _parse_amount(self, row: list, mapping: ColumnMapping) -> Decimal | None:
        if mapping.amount_col is not None:
            raw = self._get_cell(row, mapping.amount_col)
            return self._clean_decimal(raw)

        if mapping.debit_col is not None or mapping.credit_col is not None:
            debit_raw = self._get_cell(row, mapping.debit_col)
            credit_raw = self._get_cell(row, mapping.credit_col)

            debit = self._clean_decimal(debit_raw)
            credit = self._clean_decimal(credit_raw)

            if debit and debit != Decimal('0'):
                return -abs(debit)
            if credit and credit != Decimal('0'):
                return abs(credit)
            if debit == Decimal('0') and credit == Decimal('0'):
                return Decimal('0')

        return None

    def _clean_decimal(self, raw: str) -> Decimal | None:
        if not raw:
            return None
        # Remove currency symbols, spaces, and normalize decimal separators
        cleaned = raw.strip().replace(' ', '').replace('\u00a0', '')
        cleaned = re.sub(r'[€$£]', '', cleaned)
        cleaned = cleaned.replace('+', '')

        # Handle French decimal format: 1.234,56 → 1234.56
        if ',' in cleaned and '.' in cleaned:
            if cleaned.index('.') < cleaned.index(','):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')

        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
```

- [ ] **Step 4: Implement BankImportNormalizer**

```python
# ai_agent/services/normalizers/bank_import.py
from decimal import Decimal

from ai_agent.services.parsers.csv_parser import RawBankRow
from .base import BaseNormalizer


class BankImportNormalizer(BaseNormalizer):

    def normalize(self, user, row: RawBankRow, import_id: int) -> 'UnifiedTransaction':
        if row.amount < 0:
            direction = 'outflow'
            amount = abs(row.amount)
        else:
            direction = 'inflow'
            amount = row.amount

        return self._build(
            user=user,
            source_type='bank_import',
            source_id=f'import_{import_id}_{row.date}_{row.label[:50]}_{row.amount}',
            direction=direction,
            category='other',
            amount=amount,
            currency=row.currency,
            transaction_date=row.date,
            vendor_name=row.label,
            description=row.label,
            confidence=0.90,
        )
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python manage.py test ai_agent.tests.test_parsers -v 2`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add ai_agent/services/parsers/ ai_agent/services/normalizers/bank_import.py ai_agent/tests/test_parsers.py
git commit -m "feat: add CSV bank statement parser with multi-bank support"
```

---

## Task 8: Bank Import API Views

**Files:**
- Create: `core/views/bank_import.py`
- Modify: `core/urls.py`

- [ ] **Step 1: Implement bank import views**

```python
# core/views/bank_import.py
import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import BankFileImport, UnifiedTransaction
from ai_agent.services.normalizers.bank_import import BankImportNormalizer
from ai_agent.services.parsers.csv_parser import CSVBankParser

logger = logging.getLogger(__name__)


class BankFileUploadView(APIView):
    """POST /api/v1/companies/{company_pk}/bank-import/upload/"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, company_pk):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Detect file type
        filename = file.name.lower()
        if filename.endswith('.csv'):
            file_type = 'csv'
        elif filename.endswith(('.ofx', '.qfx')):
            file_type = 'ofx'
        elif filename.endswith('.xml'):
            file_type = 'camt053'
        else:
            return Response(
                {'error': f'Unsupported file type: {filename}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create import record
        bank_import = BankFileImport.objects.create(
            user=request.user,
            file=file,
            file_type=file_type,
            status='parsing',
        )

        # Parse
        file_content = file.read()

        if file_type == 'csv':
            parser = CSVBankParser()
            result = parser.parse(file_content, filename=file.name)
        else:
            bank_import.status = 'failed'
            bank_import.error_message = f'{file_type} parser not yet implemented'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': f'{file_type} parser not yet implemented',
            }, status=status.HTTP_501_NOT_IMPLEMENTED)

        if not result or not result.transactions:
            bank_import.status = 'failed'
            bank_import.error_message = 'Could not parse any transactions from file'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': 'Could not parse file. Check the format.',
                'warnings': result.warnings if result else [],
            }, status=status.HTTP_400_BAD_REQUEST)

        bank_import.bank_name = result.bank_name or ''
        bank_import.rows_total = len(result.transactions)
        if result.date_range:
            bank_import.date_from = result.date_range[0]
            bank_import.date_to = result.date_range[1]

        # Import transactions
        normalizer = BankImportNormalizer()
        imported = 0
        skipped = 0

        for row in result.transactions:
            try:
                ut = normalizer.normalize(request.user, row, bank_import.id)
                ut.save()
                imported += 1
            except IntegrityError:
                skipped += 1
            except Exception as e:
                logger.error(f'[BankImport] Error importing row: {e}')
                skipped += 1

        bank_import.rows_imported = imported
        bank_import.rows_skipped = skipped
        bank_import.status = 'parsed'
        bank_import.parser_used = f'csv_{result.bank_name}' if result.bank_name else 'csv_heuristic'
        bank_import.save()

        return Response({
            'status': 'imported',
            'import_id': bank_import.id,
            'bank_name': result.bank_name,
            'rows_total': len(result.transactions),
            'rows_imported': imported,
            'rows_skipped': skipped,
            'date_range': [str(d) for d in result.date_range] if result.date_range else None,
            'warnings': result.warnings[:10],
        })


class BankImportListView(APIView):
    """GET /api/v1/companies/{company_pk}/bank-import/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        imports = BankFileImport.objects.filter(user=request.user).order_by('-uploaded_at')[:20]
        data = [
            {
                'id': imp.id,
                'file_type': imp.file_type,
                'bank_name': imp.bank_name,
                'status': imp.status,
                'rows_total': imp.rows_total,
                'rows_imported': imp.rows_imported,
                'rows_skipped': imp.rows_skipped,
                'date_from': str(imp.date_from) if imp.date_from else None,
                'date_to': str(imp.date_to) if imp.date_to else None,
                'uploaded_at': imp.uploaded_at.isoformat(),
            }
            for imp in imports
        ]
        return Response(data)
```

- [ ] **Step 2: Add routes to core/urls.py**

Add these lines inside the company-scoped URL patterns in `core/urls.py`:

```python
# Bank import
path('companies/<uuid:company_pk>/bank-import/upload/', bank_import.BankFileUploadView.as_view(), name='bank-import-upload'),
path('companies/<uuid:company_pk>/bank-import/', bank_import.BankImportListView.as_view(), name='bank-import-list'),
```

And add the import at the top:

```python
from core.views import bank_import
```

- [ ] **Step 3: Commit**

```bash
git add core/views/bank_import.py core/urls.py
git commit -m "feat: add bank file import API (CSV upload + parsing)"
```

---

## Task 9: Unified Transaction & Cluster API + Serializers

**Files:**
- Modify: `core/serializers.py`
- Create: `core/views/unified_transactions.py`
- Create: `core/views/clusters.py`
- Modify: `core/urls.py`

- [ ] **Step 1: Add serializers**

Add these to `core/serializers.py`:

```python
# Add at the end of core/serializers.py

from ai_agent.models import UnifiedTransaction, TransactionCluster


class UnifiedTransactionSerializer(serializers.ModelSerializer):
    reconciliation_status = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedTransaction
        fields = [
            'id', 'public_id', 'source_type', 'source_id', 'evidence_role',
            'direction', 'category', 'amount', 'currency',
            'amount_tax_excl', 'tax_amount', 'tax_rate',
            'transaction_date', 'vendor_name', 'vendor_name_normalized',
            'description', 'reference', 'payment_method', 'items',
            'confidence', 'completeness',
            'pcg_code', 'pcg_label', 'business_personal', 'tva_deductible',
            'cluster', 'created_at',
        ]

    def get_reconciliation_status(self, obj):
        if not obj.cluster_id:
            return 'orphan'
        if obj.cluster and obj.cluster.is_complete:
            return 'matched'
        return 'pending'


class TransactionClusterSerializer(serializers.ModelSerializer):
    transactions = UnifiedTransactionSerializer(many=True, read_only=True)
    transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = TransactionCluster
        fields = [
            'id', 'public_id', 'label', 'cluster_type',
            'total_revenue', 'total_cost', 'margin',
            'total_tax_collected', 'total_tax_deductible',
            'confidence', 'is_complete', 'corroboration_score',
            'verification_status', 'match_reasoning', 'evidence_summary',
            'created_by', 'transactions', 'transactions_count',
            'created_at', 'updated_at',
        ]

    def get_transactions_count(self, obj):
        return obj.transactions.count()


class TransactionClusterListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no nested transactions)."""
    transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = TransactionCluster
        fields = [
            'id', 'public_id', 'label', 'cluster_type',
            'total_revenue', 'total_cost', 'margin',
            'confidence', 'is_complete', 'corroboration_score',
            'verification_status', 'transactions_count',
            'created_at',
        ]

    def get_transactions_count(self, obj):
        return obj.transactions.count()
```

- [ ] **Step 2: Create unified transaction views**

```python
# core/views/unified_transactions.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import UnifiedTransaction
from core.serializers import UnifiedTransactionSerializer


class UnifiedTransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        qs = UnifiedTransaction.objects.filter(user=request.user)

        # Filters
        source = request.query_params.get('source')
        if source:
            qs = qs.filter(source_type=source)

        direction = request.query_params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        reconciliation_status = request.query_params.get('status')
        if reconciliation_status == 'matched':
            qs = qs.filter(cluster__isnull=False, cluster__is_complete=True)
        elif reconciliation_status == 'pending':
            qs = qs.filter(cluster__isnull=False, cluster__is_complete=False)
        elif reconciliation_status == 'orphan':
            qs = qs.filter(cluster__isnull=True)

        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 100)
        start = (page - 1) * page_size
        end = start + page_size

        total = qs.count()
        transactions = qs[start:end]

        serializer = UnifiedTransactionSerializer(transactions, many=True)

        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        })
```

- [ ] **Step 3: Create cluster views**

```python
# core/views/clusters.py
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import TransactionCluster
from core.serializers import TransactionClusterSerializer, TransactionClusterListSerializer


class ClusterListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        qs = TransactionCluster.objects.filter(user=request.user)

        cluster_type = request.query_params.get('type')
        if cluster_type:
            qs = qs.filter(cluster_type=cluster_type)

        verification = request.query_params.get('verification')
        if verification:
            qs = qs.filter(verification_status=verification)

        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 50)
        start = (page - 1) * page_size
        end = start + page_size

        total = qs.count()
        clusters = qs[start:end]

        serializer = TransactionClusterListSerializer(clusters, many=True)

        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
        })


class ClusterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk, pk):
        try:
            cluster = TransactionCluster.objects.prefetch_related(
                'transactions'
            ).get(pk=pk, user=request.user)
        except TransactionCluster.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TransactionClusterSerializer(cluster)
        return Response(serializer.data)


class ClusterVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, company_pk, pk):
        try:
            cluster = TransactionCluster.objects.get(pk=pk, user=request.user)
        except TransactionCluster.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        cluster.verification_status = 'verified'
        cluster.save()
        return Response({'status': 'verified', 'cluster_id': cluster.id})
```

- [ ] **Step 4: Add routes to core/urls.py**

Add inside the company-scoped patterns:

```python
from core.views import unified_transactions, clusters

# Unified transactions
path('companies/<uuid:company_pk>/unified-transactions/', unified_transactions.UnifiedTransactionListView.as_view(), name='unified-transactions-list'),

# Clusters
path('companies/<uuid:company_pk>/clusters/', clusters.ClusterListView.as_view(), name='clusters-list'),
path('companies/<uuid:company_pk>/clusters/<int:pk>/', clusters.ClusterDetailView.as_view(), name='clusters-detail'),
path('companies/<uuid:company_pk>/clusters/<int:pk>/verify/', clusters.ClusterVerifyView.as_view(), name='clusters-verify'),
```

- [ ] **Step 5: Commit**

```bash
git add core/serializers.py core/views/unified_transactions.py core/views/clusters.py core/urls.py
git commit -m "feat: add API endpoints for UnifiedTransactions and TransactionClusters"
```

---

## Task 10: Settings Update

**Files:**
- Modify: `nova_ledger/settings.py`

- [ ] **Step 1: Add new settings for the unified pipeline**

Add after the existing AI settings block in `nova_ledger/settings.py`:

```python
# Unified Pipeline settings
AI_MODEL_ENRICHMENT = os.environ.get('AI_MODEL_ENRICHMENT', 'claude-sonnet-4-5-20250929')
AI_MODEL_CORRELATION_WORKER = os.environ.get('AI_MODEL_CORRELATION_WORKER', 'claude-sonnet-4-5-20250929')
AI_MODEL_CORRELATION_VERIFIER = os.environ.get('AI_MODEL_CORRELATION_VERIFIER', 'claude-sonnet-4-5-20250929')
AI_MODEL_VERIFICATION = os.environ.get('AI_MODEL_VERIFICATION', 'claude-haiku-4-5-20251001')

AI_ENRICHMENT_BATCH_SIZE = int(os.environ.get('AI_ENRICHMENT_BATCH_SIZE', 20))
AI_CORRELATION_BATCH_SIZE = int(os.environ.get('AI_CORRELATION_BATCH_SIZE', 30))
AI_PHASE_TIMEOUT_SECONDS = int(os.environ.get('AI_PHASE_TIMEOUT_SECONDS', 600))

# Bank import settings
BANK_IMPORT_MAX_FILE_SIZE = int(os.environ.get('BANK_IMPORT_MAX_FILE_SIZE', 10 * 1024 * 1024))  # 10MB
BANK_IMPORT_SUPPORTED_FORMATS = ['csv', 'ofx', 'qfx', 'xml']
```

- [ ] **Step 2: Commit**

```bash
git add nova_ledger/settings.py
git commit -m "feat: add settings for unified pipeline and bank import"
```

---

## Task 11: Migration Command — Migrate Existing Data

**Files:**
- Create: `ai_agent/management/__init__.py`
- Create: `ai_agent/management/commands/__init__.py`
- Create: `ai_agent/management/commands/migrate_to_unified_ledger.py`

- [ ] **Step 1: Implement migration command**

```python
# ai_agent/management/__init__.py
```

```python
# ai_agent/management/commands/__init__.py
```

```python
# ai_agent/management/commands/migrate_to_unified_ledger.py
"""
One-time migration: convert existing provider data to UnifiedTransactions.

Idempotent — can run multiple times safely (unique constraint prevents duplicates).

Usage: python manage.py migrate_to_unified_ledger [--user EMAIL]
"""
import logging

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import IntegrityError

from ai_agent.services.agents.ingestion import IngestionAgent

logger = logging.getLogger(__name__)
User = get_user_model()


class Command(BaseCommand):
    help = 'Migrate existing provider data to UnifiedTransaction ledger'

    def add_arguments(self, parser):
        parser.add_argument('--user', type=str, help='Migrate only this user (email)')

    def handle(self, *args, **options):
        if options.get('user'):
            users = User.objects.filter(email=options['user'])
        else:
            users = User.objects.all()

        agent = IngestionAgent()

        for user in users:
            self.stdout.write(f'Migrating data for {user.email}...')
            result = agent.execute(user, context={})
            self.stdout.write(
                f'  Created: {result.stats.get("created", 0)}, '
                f'Skipped: {result.stats.get("skipped", 0)}, '
                f'Errors: {len(result.errors)}'
            )
            if result.errors:
                for err in result.errors[:5]:
                    self.stdout.write(self.style.WARNING(f'  Error: {err}'))

        self.stdout.write(self.style.SUCCESS('Migration complete.'))
```

- [ ] **Step 2: Run the migration command to test**

Run: `python manage.py migrate_to_unified_ledger --user test@example.com`
Expected: Processes without errors (may have 0 items if no test data)

- [ ] **Step 3: Commit**

```bash
git add ai_agent/management/
git commit -m "feat: add management command to migrate existing data to unified ledger"
```

---

## Summary

| Task | Description | LLM | Key Files |
|------|-------------|-----|-----------|
| 1 | Unified vendor normalization | No | `normalization.py` |
| 2 | Data models (3 new) | No | `models.py` |
| 3 | Source normalizers (5 providers) | No | `normalizers/*.py` |
| 4 | Base agent framework | No | `agents/base.py` |
| 5 | Specialized agents (5 phases) | Yes | `agents/*.py`, `tools.py` |
| 6 | Pipeline orchestrator | No | `orchestrator.py` |
| 7 | CSV bank parser | No | `parsers/csv_parser.py` |
| 8 | Bank import API | No | `core/views/bank_import.py` |
| 9 | Unified Transaction & Cluster API | No | `core/views/`, `serializers.py` |
| 10 | Settings | No | `settings.py` |
| 11 | Data migration command | No | `management/commands/` |
