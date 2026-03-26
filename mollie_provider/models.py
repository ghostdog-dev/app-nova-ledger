from django.conf import settings
from django.db import models


class MollieConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mollie_connection')
    api_key = models.TextField()  # WARNING: Encrypt before production (use django-fernet-fields or similar)
    organization_id = models.CharField(max_length=255, blank=True)
    organization_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'MollieConnection({self.user.email}, org={self.organization_name})'


class MolliePayment(models.Model):
    """Mollie payment -- incoming payment from customer."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mollie_payments')
    connection = models.ForeignKey(MollieConnection, on_delete=models.CASCADE, related_name='payments')
    mollie_id = models.CharField(max_length=255, unique=True)  # tr_xxx

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    settlement_currency = models.CharField(max_length=3, blank=True)

    status = models.CharField(max_length=30)  # open, canceled, pending, authorized, expired, failed, paid
    description = models.TextField(blank=True)

    # Mollie-specific: payment method details
    method = models.CharField(max_length=30, blank=True)  # ideal, creditcard, bancontact, sofort, banktransfer, etc.

    # Card details (if method=creditcard)
    card_holder = models.CharField(max_length=255, blank=True)
    card_number = models.CharField(max_length=20, blank=True)  # masked
    card_brand = models.CharField(max_length=20, blank=True)  # visa, mastercard
    card_country = models.CharField(max_length=2, blank=True)
    card_security = models.CharField(max_length=20, blank=True)  # normal, 3dsecure

    # iDEAL details (if method=ideal)
    ideal_consumer_name = models.CharField(max_length=255, blank=True)
    ideal_consumer_account = models.CharField(max_length=34, blank=True)  # IBAN
    ideal_consumer_bic = models.CharField(max_length=11, blank=True)

    # SEPA details (if method=banktransfer)
    bank_transfer_reference = models.CharField(max_length=255, blank=True)

    # Mollie-specific: redirect & webhooks
    redirect_url = models.URLField(blank=True)
    webhook_url = models.URLField(blank=True)

    # Mollie-specific: metadata and order
    order_id = models.CharField(max_length=255, blank=True)
    metadata = models.JSONField(default=dict)

    # Mollie-specific: locale
    locale = models.CharField(max_length=10, blank=True)  # en_US, fr_FR, nl_NL
    country_code = models.CharField(max_length=2, blank=True)

    # Dates
    created_at_mollie = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    canceled_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_mollie']
        indexes = [models.Index(fields=['user', 'created_at_mollie'])]

    def __str__(self):
        return f'MolliePayment({self.mollie_id}, {self.amount} {self.currency}, {self.status})'


class MollieRefund(models.Model):
    """Mollie refund."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mollie_refunds')
    connection = models.ForeignKey(MollieConnection, on_delete=models.CASCADE, related_name='refunds')
    mollie_id = models.CharField(max_length=255, unique=True)  # re_xxx
    payment_id = models.CharField(max_length=255)  # tr_xxx

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    settlement_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    status = models.CharField(max_length=30)  # queued, pending, processing, refunded, failed
    description = models.TextField(blank=True)

    created_at_mollie = models.DateTimeField()

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_mollie']

    def __str__(self):
        return f'MollieRefund({self.mollie_id}, {self.amount} {self.currency}, {self.status})'


class MollieSettlement(models.Model):
    """Mollie settlement -- payout to merchant bank account."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mollie_settlements')
    connection = models.ForeignKey(MollieConnection, on_delete=models.CASCADE, related_name='settlements')
    mollie_id = models.CharField(max_length=255, unique=True)  # stl_xxx

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)  # open, pending, paidout, failed

    # Mollie-specific: settlement periods and revenue breakdown
    periods = models.JSONField(default=dict)  # {year: {month: {revenue, costs, invoiceId}}}

    settled_at = models.DateTimeField(null=True, blank=True)
    created_at_mollie = models.DateTimeField()

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_mollie']

    def __str__(self):
        return f'MollieSettlement({self.mollie_id}, {self.amount} {self.currency}, {self.status})'


class MollieInvoice(models.Model):
    """Mollie invoice -- Mollie's fee invoice to the merchant."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='mollie_invoices')
    connection = models.ForeignKey(MollieConnection, on_delete=models.CASCADE, related_name='invoices')
    mollie_id = models.CharField(max_length=255, unique=True)

    reference = models.CharField(max_length=100, blank=True)
    vat_number = models.CharField(max_length=50, blank=True)

    gross_amount = models.DecimalField(max_digits=12, decimal_places=2)
    net_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)

    status = models.CharField(max_length=30)  # open, paid, overdue

    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    pdf_url = models.URLField(blank=True)

    lines = models.JSONField(default=list)  # line items

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issued_at']

    def __str__(self):
        return f'MollieInvoice({self.mollie_id}, {self.gross_amount} {self.currency}, {self.status})'
