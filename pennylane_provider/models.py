from django.conf import settings
from django.db import models


class PennylaneConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pennylane_connection')
    access_token = models.TextField()  # Bearer token from Pennylane UI — WARNING: encrypt before production
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'PennylaneConnection({self.user.email}, account={self.account_name})'


class PennylaneCustomerInvoice(models.Model):
    """Pennylane customer invoice — facture client."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pennylane_customer_invoices')
    connection = models.ForeignKey(PennylaneConnection, on_delete=models.CASCADE, related_name='customer_invoices')
    pennylane_id = models.CharField(max_length=255, unique=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30)  # draft/pending/accepted/paid/cancelled/etc
    date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_id_pennylane = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # total HT
    currency = models.CharField(max_length=3, default='EUR')
    tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)  # TTC
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_items = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['user', 'date'])]

    def __str__(self):
        return f'PennylaneCustomerInvoice({self.pennylane_id}, {self.amount} {self.currency}, {self.status})'


class PennylaneSupplierInvoice(models.Model):
    """Pennylane supplier invoice — facture fournisseur."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pennylane_supplier_invoices')
    connection = models.ForeignKey(PennylaneConnection, on_delete=models.CASCADE, related_name='supplier_invoices')
    pennylane_id = models.CharField(max_length=255, unique=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30)
    date = models.DateField(null=True, blank=True)
    deadline = models.DateField(null=True, blank=True)
    supplier_name = models.CharField(max_length=255, blank=True)
    supplier_id_pennylane = models.CharField(max_length=255, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)  # total HT
    currency = models.CharField(max_length=3, default='EUR')
    tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2)  # TTC
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    remaining_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    line_items = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['user', 'date'])]

    def __str__(self):
        return f'PennylaneSupplierInvoice({self.pennylane_id}, {self.amount} {self.currency}, {self.status})'


class PennylaneTransaction(models.Model):
    """Pennylane bank transaction."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='pennylane_transactions')
    connection = models.ForeignKey(PennylaneConnection, on_delete=models.CASCADE, related_name='transactions')
    pennylane_id = models.CharField(max_length=255, unique=True)
    date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='EUR')
    label = models.TextField(blank=True)
    bank_account_name = models.CharField(max_length=255, blank=True)
    category = models.CharField(max_length=255, blank=True)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']
        indexes = [models.Index(fields=['user', 'date'])]

    def __str__(self):
        return f'PennylaneTransaction({self.pennylane_id}, {self.amount} {self.currency})'
