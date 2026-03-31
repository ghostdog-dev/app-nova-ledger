import uuid
from decimal import Decimal

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from ai_agent.services.normalization import normalize_vendor


class PipelineRun(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending'
        TRIAGE = 'triage'
        EXTRACTION = 'extraction'
        MERGE = 'merge'
        COMPUTATION = 'computation'
        BANK_CORRELATION = 'bank_correlation'
        PROVIDER_CORRELATION = 'provider_correlation'
        CLASSIFICATION = 'classification'
        RECURRING = 'recurring'
        COMPLETE = 'complete'
        FAILED = 'failed'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=30, choices=Status.choices, default=Status.PENDING)
    current_pass = models.IntegerField(default=0)
    state = models.JSONField(default=dict)
    error_message = models.TextField(blank=True, default='')
    stats = models.JSONField(default=dict)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']

    def __str__(self):
        return f'PipelineRun #{self.pk} ({self.status}) for {self.user}'


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
