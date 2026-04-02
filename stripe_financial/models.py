"""
Stripe Financial Connections — bank account data via Stripe.

Stores linked bank accounts, transactions, balances, and ownership data
fetched through Stripe's Financial Connections API.
"""
from django.conf import settings
from django.db import models


class FinancialAccount(models.Model):
    """A bank account linked via Stripe Financial Connections."""

    class Status(models.TextChoices):
        ACTIVE = 'active'
        INACTIVE = 'inactive'
        DISCONNECTED = 'disconnected'

    class Category(models.TextChoices):
        CASH = 'cash'
        CREDIT = 'credit'
        INVESTMENT = 'investment'
        OTHER = 'other'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='financial_accounts',
    )
    # Stripe IDs
    stripe_account_id = models.CharField(max_length=255, unique=True)  # fca_xxx
    stripe_customer_id = models.CharField(max_length=255, blank=True)  # cus_xxx

    # Account info (available without extra permissions)
    display_name = models.CharField(max_length=255, blank=True)
    institution_name = models.CharField(max_length=255, blank=True)
    last4 = models.CharField(max_length=4, blank=True)
    category = models.CharField(max_length=20, choices=Category.choices, blank=True)
    subcategory = models.CharField(max_length=50, blank=True)  # checking, savings, credit_card
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)

    # Permissions granted by the user
    permissions = models.JSONField(default=list)  # ["transactions", "balances", "ownership"]

    # Balance data (refreshed separately)
    balance_current = models.JSONField(null=True, blank=True)  # {"eur": 6000} in cents
    balance_available = models.JSONField(null=True, blank=True)  # {"eur": 5500}
    balance_type = models.CharField(max_length=10, blank=True)  # cash or credit
    balance_as_of = models.DateTimeField(null=True, blank=True)
    balance_refresh_status = models.CharField(max_length=20, blank=True)

    # Ownership data (refreshed separately)
    ownership_data = models.JSONField(default=list)  # [{name, email, phone, raw_address}]
    ownership_refresh_status = models.CharField(max_length=20, blank=True)

    # Transaction subscription
    transaction_refresh_status = models.CharField(max_length=20, blank=True)
    transaction_subscribed = models.BooleanField(default=False)
    last_transaction_refresh_id = models.CharField(max_length=255, blank=True)

    # Metadata
    raw_data = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['user', 'status'])]

    def __str__(self):
        return f'{self.institution_name} {self.display_name} (*{self.last4})'


class FinancialTransaction(models.Model):
    """A bank transaction fetched via Stripe Financial Connections."""

    class Status(models.TextChoices):
        PENDING = 'pending'
        POSTED = 'posted'
        VOID = 'void'

    account = models.ForeignKey(
        FinancialAccount, on_delete=models.CASCADE, related_name='transactions',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='financial_transactions',
    )
    stripe_transaction_id = models.CharField(max_length=255, unique=True)  # fctxn_xxx

    # Core transaction data
    amount = models.IntegerField()  # in cents, negative = debit
    currency = models.CharField(max_length=3)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=Status.choices)

    # Timestamps
    transacted_at = models.DateTimeField()
    posted_at = models.DateTimeField(null=True, blank=True)
    void_at = models.DateTimeField(null=True, blank=True)

    # Refresh tracking
    transaction_refresh_id = models.CharField(max_length=255, blank=True)

    # Raw Stripe data for debugging/exploration
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-transacted_at']
        indexes = [
            models.Index(fields=['user', 'transacted_at']),
            models.Index(fields=['account', 'transacted_at']),
        ]

    @property
    def amount_decimal(self):
        return self.amount / 100

    def __str__(self):
        return f'{self.description[:50]} {self.amount_decimal} {self.currency}'
