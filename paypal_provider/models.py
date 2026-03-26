from django.conf import settings
from django.db import models


class PayPalConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paypal_connection')
    client_id = models.CharField(max_length=255)
    client_secret = models.TextField()  # WARNING: Encrypt before production (use django-fernet-fields or similar)
    account_email = models.CharField(max_length=255, blank=True)
    is_sandbox = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'PayPalConnection({self.user.email}, sandbox={self.is_sandbox})'


class PayPalTransaction(models.Model):
    """PayPal transaction -- payment received or sent."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paypal_transactions')
    connection = models.ForeignKey(PayPalConnection, on_delete=models.CASCADE, related_name='transactions')
    paypal_id = models.CharField(max_length=255, unique=True)  # transaction_id

    # Amounts
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    fee = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    net = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # PayPal-specific
    event_code = models.CharField(max_length=10, blank=True)  # T0006, T1107, etc.
    transaction_status = models.CharField(max_length=30, blank=True)  # S, V, P, D

    description = models.TextField(blank=True)
    note = models.TextField(blank=True)

    # Payer info
    payer_email = models.CharField(max_length=255, blank=True)
    payer_name = models.CharField(max_length=255, blank=True)
    payer_id = models.CharField(max_length=255, blank=True)

    # PayPal-specific: protection
    protection_eligibility = models.CharField(max_length=50, blank=True)  # ELIGIBLE, NOT_ELIGIBLE

    # References
    invoice_id = models.CharField(max_length=255, blank=True)
    custom_field = models.TextField(blank=True)

    # Dates
    initiation_date = models.DateTimeField()
    updated_date = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-initiation_date']
        indexes = [models.Index(fields=['user', 'initiation_date'])]

    def __str__(self):
        return f'PayPalTransaction({self.paypal_id}, {self.amount} {self.currency})'


class PayPalInvoice(models.Model):
    """PayPal invoice -- invoices sent to customers."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paypal_invoices')
    connection = models.ForeignKey(PayPalConnection, on_delete=models.CASCADE, related_name='invoices')
    paypal_id = models.CharField(max_length=255, unique=True)

    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30)  # DRAFT, SENT, PAID, CANCELLED

    amount_total = models.DecimalField(max_digits=12, decimal_places=2)
    amount_due = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)

    # PayPal-specific
    merchant_memo = models.TextField(blank=True)
    terms_and_conditions = models.TextField(blank=True)

    # Recipient
    recipient_email = models.CharField(max_length=255, blank=True)
    recipient_name = models.CharField(max_length=255, blank=True)

    invoice_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    # PayPal-specific: payment tracking
    payments = models.JSONField(default=list)  # [{date, amount, method}]
    refunds = models.JSONField(default=list)

    line_items = models.JSONField(default=list)  # [{name, quantity, unit_amount, tax}]

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-invoice_date']

    def __str__(self):
        return f'PayPalInvoice({self.invoice_number}, {self.status})'


class PayPalDispute(models.Model):
    """PayPal dispute/claim."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='paypal_disputes')
    connection = models.ForeignKey(PayPalConnection, on_delete=models.CASCADE, related_name='disputes')
    paypal_id = models.CharField(max_length=255, unique=True)

    disputed_transaction_id = models.CharField(max_length=255, blank=True)
    reason = models.CharField(max_length=100, blank=True)  # MERCHANDISE_OR_SERVICE_NOT_RECEIVED, etc.
    status = models.CharField(max_length=30)  # OPEN, WAITING_FOR_BUYER_RESPONSE, RESOLVED, etc.
    dispute_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    currency = models.CharField(max_length=3, blank=True)

    # PayPal-specific
    dispute_outcome = models.CharField(max_length=50, blank=True)  # RESOLVED_BUYER_FAVOUR, etc.
    dispute_life_cycle_stage = models.CharField(max_length=30, blank=True)

    created_date = models.DateTimeField(null=True, blank=True)
    updated_date = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_date']

    def __str__(self):
        return f'PayPalDispute({self.paypal_id}, {self.status})'
