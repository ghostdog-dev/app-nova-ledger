from django.conf import settings
from django.db import models


class SumUpConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sumup_connection')
    api_key = models.TextField()  # sup_sk_... — WARNING: encrypt before production
    merchant_code = models.CharField(max_length=20)
    merchant_name = models.CharField(max_length=255, blank=True)
    default_currency = models.CharField(max_length=3, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'SumUpConnection({self.user.email}, merchant={self.merchant_name})'


class SumUpTransaction(models.Model):
    """SumUp transaction -- card payment, refund, or charge-back."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sumup_transactions')
    connection = models.ForeignKey(SumUpConnection, on_delete=models.CASCADE, related_name='transactions')
    sumup_id = models.CharField(max_length=64, unique=True)  # UUID

    transaction_code = models.CharField(max_length=32, blank=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tip_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    fee_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    refunded_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3)

    timestamp = models.DateTimeField()  # transaction time
    status = models.CharField(max_length=20)  # SUCCESSFUL, CANCELLED, FAILED, PENDING, REFUNDED, CHARGE_BACK
    type = models.CharField(max_length=20)  # PAYMENT, REFUND, CHARGE_BACK
    payment_type = models.CharField(max_length=20, blank=True)  # ECOM, POS, CASH, RECURRING, etc.
    entry_mode = models.CharField(max_length=30, blank=True)

    card_type = models.CharField(max_length=20, blank=True)  # VISA, MASTERCARD, AMEX, MAESTRO
    card_last4 = models.CharField(max_length=4, blank=True)

    product_summary = models.TextField(blank=True)
    installments_count = models.IntegerField(default=1)

    payout_date = models.DateField(null=True, blank=True)
    payout_type = models.CharField(max_length=30, blank=True)
    auth_code = models.CharField(max_length=16, blank=True)
    internal_id = models.BigIntegerField(null=True, blank=True)

    products = models.JSONField(default=list)  # line items
    vat_rates = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [models.Index(fields=['user', 'timestamp'])]

    def __str__(self):
        return f'SumUpTransaction({self.sumup_id}, {self.amount} {self.currency}, {self.status})'


class SumUpPayout(models.Model):
    """SumUp payout -- transfer to merchant bank account."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='sumup_payouts')
    connection = models.ForeignKey(SumUpConnection, on_delete=models.CASCADE, related_name='payouts')
    sumup_id = models.IntegerField(unique=True)  # integer ID

    amount = models.DecimalField(max_digits=10, decimal_places=2)  # can be negative
    currency = models.CharField(max_length=3)
    date = models.DateField()
    fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(max_length=20)  # SUCCESSFUL, FAILED
    type = models.CharField(max_length=30)  # PAYOUT, CHARGE_BACK_DEDUCTION, REFUND_DEDUCTION, etc.
    reference = models.CharField(max_length=64, blank=True)
    transaction_code = models.CharField(max_length=32, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'SumUpPayout({self.sumup_id}, {self.amount} {self.currency}, {self.status})'
