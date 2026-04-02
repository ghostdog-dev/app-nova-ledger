from django.conf import settings
from django.db import models


class AlmaConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alma_connection')
    api_key = models.TextField()  # sk_test_... or sk_live_... — WARNING: encrypt before production
    is_sandbox = models.BooleanField(default=True)
    merchant_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'AlmaConnection({self.user.email}, sandbox={self.is_sandbox})'


class AlmaPayment(models.Model):
    """Alma payment -- BNPL installment payment."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alma_payments')
    connection = models.ForeignKey(AlmaConnection, on_delete=models.CASCADE, related_name='payments')
    alma_id = models.CharField(max_length=255, unique=True)  # payment_xxx

    state = models.CharField(max_length=30)  # not_started, scored_no, scored_yes, scored_maybe, paid
    processing_status = models.CharField(max_length=30, blank=True)  # awaiting_authorization, authorized, captured, canceled

    purchase_amount = models.IntegerField()  # cents
    customer_fee = models.IntegerField(default=0)  # cents
    installments_count = models.IntegerField()
    kind = models.CharField(max_length=20, blank=True)  # P1X, P2X, P3X, P4X, P10X

    customer_email = models.CharField(max_length=255, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)
    customer_phone = models.CharField(max_length=50, blank=True)

    merchant_reference = models.CharField(max_length=255, blank=True)  # from orders[0].merchant_reference

    payment_plan = models.JSONField(default=list)  # [{state, purchase_amount, total_amount, due_date, date_paid}]
    refunds = models.JSONField(default=list)
    amount_already_refunded = models.IntegerField(default=0)
    is_completely_refunded = models.BooleanField(default=False)

    payout_status = models.CharField(max_length=30, blank=True)
    currency = models.CharField(max_length=3, default='EUR')

    raw_data = models.JSONField(default=dict)
    created_at_alma = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_alma']
        indexes = [models.Index(fields=['user', 'created_at_alma'])]

    def __str__(self):
        return f'AlmaPayment({self.alma_id}, {self.purchase_amount}c {self.currency}, {self.state})'

    @property
    def purchase_amount_decimal(self):
        return self.purchase_amount / 100
