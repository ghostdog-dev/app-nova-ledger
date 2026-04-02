from django.conf import settings
from django.db import models


class BankFileImport(models.Model):
    """Record of an imported bank file."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_imports')
    original_filename = models.CharField(max_length=500)
    file_format = models.CharField(max_length=20)  # csv, xlsx, xls, ofx, qif, cfonb
    file_size = models.IntegerField(default=0)
    encoding = models.CharField(max_length=30, blank=True)
    separator = models.CharField(max_length=5, blank=True)  # for CSV
    column_mapping = models.JSONField(default=dict)  # detected mapping: {our_field: file_column}
    bank_name = models.CharField(max_length=255, blank=True)  # auto-detected or user-specified
    account_id = models.CharField(max_length=255, blank=True)
    transactions_count = models.IntegerField(default=0)
    duplicates_skipped = models.IntegerField(default=0)
    raw_preview = models.JSONField(default=list)  # first 5 rows for debugging
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.original_filename} ({self.transactions_count} txns)'


class ImportedTransaction(models.Model):
    """A bank transaction imported from a file."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='imported_transactions')
    file_import = models.ForeignKey(BankFileImport, on_delete=models.CASCADE, related_name='transactions')

    # Core financial data
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    description = models.TextField(blank=True)

    # Optional fields (detected if available)
    value_date = models.DateField(null=True, blank=True)  # date de valeur
    reference = models.CharField(max_length=255, blank=True)
    counterparty = models.CharField(max_length=255, blank=True)  # nom du tiers
    category = models.CharField(max_length=255, blank=True)
    balance_after = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    transaction_type = models.CharField(max_length=100, blank=True)  # virement, prelevement, CB, etc.

    # Dedup
    fingerprint = models.CharField(max_length=64, unique=True)  # hash for deduplication

    # Raw
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'date']),
            models.Index(fields=['fingerprint']),
        ]

    def __str__(self):
        return f'{self.date} {self.amount} {self.currency} — {self.description[:50]}'
