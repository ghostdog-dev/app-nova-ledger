from django.conf import settings
from django.db import models


class EvolizConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evoliz_connection')
    public_key = models.CharField(max_length=255)
    secret_key = models.TextField()
    company_id = models.CharField(max_length=255)
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'EvolizConnection({self.user.email}, company={self.company_id})'


class EvolizInvoice(models.Model):
    """Evoliz invoice -- sales invoice."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evoliz_invoices')
    connection = models.ForeignKey(EvolizConnection, on_delete=models.CASCADE, related_name='invoices')
    evoliz_id = models.IntegerField(unique=True)
    document_number = models.CharField(max_length=100)
    typedoc = models.CharField(max_length=30)  # invoice, retention, situation, benefit
    status = models.CharField(max_length=30)  # filled, create, sent, inpayment, paid, match, nopaid, unpaid

    documentdate = models.DateField()
    duedate = models.DateField(null=True, blank=True)

    object_label = models.TextField(blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    client_id_evoliz = models.IntegerField(null=True, blank=True)

    total_vat_exclude = models.DecimalField(max_digits=12, decimal_places=2)
    total_vat = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_vat_include = models.DecimalField(max_digits=12, decimal_places=2)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_to_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='EUR')

    items = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-documentdate']
        indexes = [models.Index(fields=['user', 'documentdate'])]

    def __str__(self):
        return f'EvolizInvoice({self.document_number}, {self.total_vat_include} {self.currency}, {self.status})'


class EvolizPurchase(models.Model):
    """Evoliz purchase -- buy/expense."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evoliz_purchases')
    connection = models.ForeignKey(EvolizConnection, on_delete=models.CASCADE, related_name='purchases')
    evoliz_id = models.IntegerField(unique=True)
    document_number = models.CharField(max_length=100)
    status = models.CharField(max_length=30)  # create, inpayment, prepare, voucher, paid, match

    documentdate = models.DateField()
    duedate = models.DateField(null=True, blank=True)

    supplier_name = models.CharField(max_length=255, blank=True)
    supplier_id_evoliz = models.IntegerField(null=True, blank=True)

    total_vat_exclude = models.DecimalField(max_digits=12, decimal_places=2)
    total_vat = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_vat_include = models.DecimalField(max_digits=12, decimal_places=2)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    net_to_pay = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='EUR')

    items = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-documentdate']
        indexes = [models.Index(fields=['user', 'documentdate'])]

    def __str__(self):
        return f'EvolizPurchase({self.document_number}, {self.total_vat_include} {self.currency}, {self.status})'


class EvolizPayment(models.Model):
    """Evoliz payment -- received payment."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='evoliz_payments')
    connection = models.ForeignKey(EvolizConnection, on_delete=models.CASCADE, related_name='payments')
    evoliz_id = models.IntegerField(unique=True)

    paydate = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    label = models.TextField(blank=True)
    client_name = models.CharField(max_length=255, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    invoice_id_evoliz = models.IntegerField(null=True, blank=True)
    paytype_label = models.CharField(max_length=100, blank=True)
    currency = models.CharField(max_length=3, default='EUR')

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paydate']
        indexes = [models.Index(fields=['user', 'paydate'])]

    def __str__(self):
        return f'EvolizPayment({self.evoliz_id}, {self.amount} {self.currency})'
