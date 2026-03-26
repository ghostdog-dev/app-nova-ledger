from django.conf import settings
from django.db import models


class PowensUser(models.Model):
    """Links a Nova Ledger user to their Powens account."""
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='powens'
    )
    powens_user_id = models.IntegerField(unique=True)
    auth_token = models.TextField()  # permanent token
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'PowensUser({self.user.email}, id={self.powens_user_id})'


class BankConnection(models.Model):
    """A connection to a specific bank via Powens."""
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_connections'
    )
    powens_connection_id = models.IntegerField(unique=True)
    bank_name = models.CharField(max_length=255, blank=True)
    state = models.CharField(max_length=50, blank=True)  # null=ok, SCARequired, wrongpass, etc.
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'BankConnection({self.bank_name}, state={self.state})'


class BankAccount(models.Model):
    """A bank account discovered via Powens."""
    connection = models.ForeignKey(
        BankConnection, on_delete=models.CASCADE, related_name='accounts'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_accounts'
    )
    powens_account_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    iban = models.CharField(max_length=34, blank=True)
    balance = models.DecimalField(max_digits=12, decimal_places=2, null=True)
    currency = models.CharField(max_length=3, default='EUR')
    account_type = models.CharField(max_length=50, blank=True)  # checking, savings, etc.
    disabled = models.BooleanField(default=False)
    last_update = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'BankAccount({self.name}, {self.iban})'


class BankTransaction(models.Model):
    """A bank transaction from Powens."""
    account = models.ForeignKey(
        BankAccount, on_delete=models.CASCADE, related_name='transactions'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='bank_transactions'
    )
    powens_transaction_id = models.IntegerField(unique=True)
    date = models.DateField()
    value = models.DecimalField(max_digits=12, decimal_places=2)  # negative=debit, positive=credit
    original_wording = models.CharField(max_length=500)  # raw bank label
    simplified_wording = models.CharField(max_length=500, blank=True)  # cleaned label
    transaction_type = models.CharField(max_length=50, blank=True)  # card, transfer, check, etc.
    coming = models.BooleanField(default=False)  # pending transaction
    card = models.CharField(max_length=20, blank=True)  # card number (masked)
    # Counterparty info
    counterparty_label = models.CharField(max_length=255, blank=True)
    counterparty_iban = models.CharField(max_length=34, blank=True)
    # Metadata
    # Real/initiation date (e.g. card swipe date, often matches email date)
    rdate = models.DateField(null=True, blank=True)
    # Cross-currency original amounts (before conversion to account currency)
    original_value = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    original_currency = models.CharField(max_length=3, blank=True)
    # Powens category
    category_id = models.IntegerField(null=True, blank=True)
    # Metadata
    raw_data = models.JSONField(default=dict)  # full Powens response for reference
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date']

    def __str__(self):
        return f'BankTransaction({self.original_wording}, {self.value})'
