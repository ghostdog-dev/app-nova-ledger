from django.conf import settings
from django.db import models


class PayPlugConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payplug_connection')
    secret_key = models.TextField()  # sk_test_... or sk_live_... — WARNING: encrypt before production
    is_live = models.BooleanField(default=False)  # derived from key prefix
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'PayPlugConnection({self.user.email}, live={self.is_live})'


class PayPlugPayment(models.Model):
    """PayPlug payment -- incoming payment from customer."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payplug_payments')
    connection = models.ForeignKey(PayPlugConnection, on_delete=models.CASCADE, related_name='payments')
    payplug_id = models.CharField(max_length=255, unique=True)  # pay_xxx

    amount = models.IntegerField()  # cents
    amount_refunded = models.IntegerField(default=0)
    currency = models.CharField(max_length=3)

    is_paid = models.BooleanField(default=False)
    is_refunded = models.BooleanField(default=False)
    is_3ds = models.BooleanField(null=True)
    description = models.TextField(blank=True)

    # Card details
    card_last4 = models.CharField(max_length=4, blank=True)
    card_brand = models.CharField(max_length=20, blank=True)  # Visa, Mastercard, Maestro, CB, Amex
    card_country = models.CharField(max_length=2, blank=True)
    card_exp_month = models.IntegerField(null=True, blank=True)
    card_exp_year = models.IntegerField(null=True, blank=True)

    # Billing details
    billing_email = models.CharField(max_length=255, blank=True)
    billing_first_name = models.CharField(max_length=255, blank=True)
    billing_last_name = models.CharField(max_length=255, blank=True)

    # Failure details
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.TextField(blank=True)

    # Installment plan
    installment_plan_id = models.CharField(max_length=255, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict)

    # Dates
    created_at_payplug = models.DateTimeField()
    paid_at = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_payplug']
        indexes = [models.Index(fields=['user', 'created_at_payplug'])]

    def __str__(self):
        return f'PayPlugPayment({self.payplug_id}, {self.amount}c {self.currency}, paid={self.is_paid})'

    @property
    def amount_decimal(self):
        return self.amount / 100


class PayPlugRefund(models.Model):
    """PayPlug refund."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='payplug_refunds')
    connection = models.ForeignKey(PayPlugConnection, on_delete=models.CASCADE, related_name='refunds')
    payplug_id = models.CharField(max_length=255, unique=True)  # re_xxx
    payment_id = models.CharField(max_length=255)  # pay_xxx

    amount = models.IntegerField()  # cents
    currency = models.CharField(max_length=3)

    metadata = models.JSONField(default=dict)

    created_at_payplug = models.DateTimeField()

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_payplug']

    def __str__(self):
        return f'PayPlugRefund({self.payplug_id}, {self.amount}c {self.currency})'
