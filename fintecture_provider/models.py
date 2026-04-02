from django.conf import settings
from django.db import models


class FintectureConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fintecture_connection')
    app_id = models.CharField(max_length=255)
    app_secret = models.TextField()  # WARNING: encrypt before production
    is_sandbox = models.BooleanField(default=True)
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'FintectureConnection({self.user.email}, sandbox={self.is_sandbox})'


class FintecturePayment(models.Model):
    """Fintecture payment -- Pay by Bank payment initiated via PIS."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fintecture_payments')
    connection = models.ForeignKey(FintectureConnection, on_delete=models.CASCADE, related_name='payments')
    session_id = models.CharField(max_length=32, unique=True)  # 32-char hex, no hyphens

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    communication = models.CharField(max_length=255, blank=True)  # payment reference
    end_to_end_id = models.CharField(max_length=64, blank=True)
    execution_date = models.DateField(null=True, blank=True)
    payment_scheme = models.CharField(max_length=20, blank=True)  # SEPA, etc.
    transfer_state = models.CharField(max_length=30, blank=True)  # completed, sent, processing, etc.

    status = models.CharField(max_length=30)  # payment_created, payment_pending, etc.
    session_type = models.CharField(max_length=30, blank=True)  # PayByBank, RequestToPay, etc.
    provider = models.CharField(max_length=20, blank=True)  # bank BIC
    customer_id = models.CharField(max_length=32, blank=True)
    bank_account_id = models.CharField(max_length=64, blank=True)

    is_accepted = models.BooleanField(default=False)
    has_settlement_completed = models.BooleanField(default=False)

    metadata = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-execution_date']
        indexes = [models.Index(fields=['user', 'execution_date'])]

    def __str__(self):
        return f'FintecturePayment({self.session_id}, {self.amount} {self.currency}, {self.status})'


class FintectureSettlement(models.Model):
    """Fintecture settlement."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='fintecture_settlements')
    connection = models.ForeignKey(FintectureConnection, on_delete=models.CASCADE, related_name='settlements')
    settlement_id = models.CharField(max_length=64, unique=True)

    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)
    execution_date = models.DateField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-execution_date']

    def __str__(self):
        return f'FintectureSettlement({self.settlement_id}, {self.amount} {self.currency}, {self.status})'
