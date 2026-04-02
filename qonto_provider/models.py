from django.conf import settings
from django.db import models


class QontoConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='qonto_connection')
    login = models.CharField(max_length=255)  # org slug
    secret_key = models.TextField()  # WARNING: encrypt before production
    organization_name = models.CharField(max_length=255, blank=True)
    iban = models.CharField(max_length=34, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'QontoConnection({self.user.email}, org={self.organization_name})'


class QontoBankAccount(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='qonto_bank_accounts')
    connection = models.ForeignKey(QontoConnection, on_delete=models.CASCADE, related_name='bank_accounts')
    qonto_id = models.CharField(max_length=64, unique=True)  # UUID
    slug = models.CharField(max_length=255, blank=True)
    name = models.CharField(max_length=255)
    iban = models.CharField(max_length=34, blank=True)
    bic = models.CharField(max_length=11, blank=True)
    currency = models.CharField(max_length=3, default='EUR')
    balance_cents = models.BigIntegerField(default=0)
    authorized_balance_cents = models.BigIntegerField(default=0)
    status = models.CharField(max_length=20, default='active')
    is_main = models.BooleanField(default=False)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    @property
    def balance(self):
        return self.balance_cents / 100

    def __str__(self):
        return f'QontoBankAccount({self.name}, {self.iban}, {self.balance} {self.currency})'


class QontoTransaction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='qonto_transactions')
    connection = models.ForeignKey(QontoConnection, on_delete=models.CASCADE, related_name='transactions')
    qonto_id = models.CharField(max_length=64, unique=True)  # UUID
    transaction_id = models.CharField(max_length=255, blank=True)  # legacy slug
    amount_cents = models.BigIntegerField()
    currency = models.CharField(max_length=3, default='EUR')
    side = models.CharField(max_length=10)  # credit / debit
    operation_type = models.CharField(max_length=50)
    status = models.CharField(max_length=20)  # pending / declined / completed
    label = models.TextField(blank=True)
    counterparty_name = models.CharField(max_length=255, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    note = models.TextField(blank=True)
    settled_at = models.DateTimeField(null=True, blank=True)
    emitted_at = models.DateTimeField(null=True, blank=True)
    category = models.CharField(max_length=100, blank=True)
    attachment_ids = models.JSONField(default=list)
    label_ids = models.JSONField(default=list)
    card_last_digits = models.CharField(max_length=4, blank=True)
    bank_account_id = models.CharField(max_length=64, blank=True)
    raw_data = models.JSONField(default=dict)
    created_at_qonto = models.DateTimeField()
    updated_at_qonto = models.DateTimeField(null=True, blank=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-settled_at']
        indexes = [models.Index(fields=['user', 'settled_at'])]

    @property
    def amount(self):
        return self.amount_cents / 100

    def __str__(self):
        return f'QontoTransaction({self.qonto_id}, {self.amount} {self.currency}, {self.side}, {self.status})'
