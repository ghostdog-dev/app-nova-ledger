from django.conf import settings
from django.db import models


class VosFacturesConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vosfactures_connection')
    api_token = models.TextField()  # WARNING: encrypt before production
    account_prefix = models.CharField(max_length=255)  # subdomain, e.g. "monentreprise"
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'VosFacturesConnection({self.user.email}, prefix={self.account_prefix})'


class VosFacturesInvoice(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vosfactures_invoices')
    connection = models.ForeignKey(VosFacturesConnection, on_delete=models.CASCADE, related_name='invoices')
    vosfactures_id = models.IntegerField(unique=True)

    number = models.CharField(max_length=100, blank=True)
    kind = models.CharField(max_length=30)  # vat, correction, estimate, proforma, advance, final, receipt
    status = models.CharField(max_length=30)  # issued, sent, paid, partial, rejected, accepted

    issue_date = models.DateField(null=True, blank=True)
    sell_date = models.CharField(max_length=20, blank=True)  # can be YYYY-MM or date
    payment_to = models.DateField(null=True, blank=True)
    paid_date = models.DateField(null=True, blank=True)

    price_net = models.DecimalField(max_digits=12, decimal_places=2)
    price_gross = models.DecimalField(max_digits=12, decimal_places=2)
    price_tax = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=3, default='EUR')

    income = models.BooleanField(default=True)  # 1=sale, 0=expense

    buyer_name = models.CharField(max_length=255, blank=True)
    buyer_tax_no = models.CharField(max_length=50, blank=True)
    client_id_vf = models.IntegerField(null=True, blank=True)
    seller_name = models.CharField(max_length=255, blank=True)
    payment_type = models.CharField(max_length=50, blank=True)

    positions = models.JSONField(default=list)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-issue_date']

    def __str__(self):
        return f'VosFacturesInvoice({self.vosfactures_id}, {self.number}, {self.price_gross} {self.currency}, {self.status})'


class VosFacturesPayment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vosfactures_payments')
    connection = models.ForeignKey(VosFacturesConnection, on_delete=models.CASCADE, related_name='payments')
    vosfactures_id = models.IntegerField(unique=True)

    price = models.DecimalField(max_digits=12, decimal_places=2)
    paid_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3)
    invoice_id_vf = models.IntegerField(null=True, blank=True)
    invoice_name = models.CharField(max_length=255, blank=True)
    provider = models.CharField(max_length=100, blank=True)  # payment method
    description = models.TextField(blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'VosFacturesPayment({self.vosfactures_id}, {self.price} {self.currency})'


class VosFacturesClient(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='vosfactures_clients')
    connection = models.ForeignKey(VosFacturesConnection, on_delete=models.CASCADE, related_name='clients')
    vosfactures_id = models.IntegerField(unique=True)

    name = models.CharField(max_length=255)
    tax_no = models.CharField(max_length=50, blank=True)
    email = models.CharField(max_length=255, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=255, blank=True)
    street = models.CharField(max_length=255, blank=True)
    post_code = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=2, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'VosFacturesClient({self.vosfactures_id}, {self.name})'
