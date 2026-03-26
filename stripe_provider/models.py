from django.conf import settings
from django.db import models


class StripeConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_connection')
    stripe_account_id = models.CharField(max_length=255)
    api_key = models.TextField()  # WARNING: Encrypt before production (use django-fernet-fields or similar)
    account_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Stripe: {self.account_name or self.stripe_account_id}'


class StripeBalanceTransaction(models.Model):
    """Stripe balance transaction — the core financial record."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_balance_transactions')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='balance_transactions')
    stripe_id = models.CharField(max_length=255, unique=True)  # txn_xxx

    amount = models.IntegerField()  # in cents
    currency = models.CharField(max_length=3)
    fee = models.IntegerField(default=0)  # in cents
    net = models.IntegerField(default=0)  # in cents

    type = models.CharField(max_length=50)  # charge, refund, payout, transfer, adjustment, stripe_fee
    status = models.CharField(max_length=30)  # available, pending
    description = models.TextField(blank=True)

    # Linked source
    source_id = models.CharField(max_length=255, blank=True)  # ch_xxx, re_xxx, po_xxx
    source_type = models.CharField(max_length=50, blank=True)  # charge, refund, payout

    created_at_stripe = models.DateTimeField()
    available_on = models.DateTimeField(null=True, blank=True)

    # Stripe-specific: exchange rate for multi-currency
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_stripe']
        indexes = [models.Index(fields=['user', 'created_at_stripe'])]

    @property
    def amount_decimal(self):
        return self.amount / 100

    @property
    def fee_decimal(self):
        return self.fee / 100

    @property
    def net_decimal(self):
        return self.net / 100


class StripeCharge(models.Model):
    """Stripe charge — payment from a customer."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_charges')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='charges')
    stripe_id = models.CharField(max_length=255, unique=True)  # ch_xxx

    amount = models.IntegerField()  # cents
    amount_captured = models.IntegerField(default=0)
    amount_refunded = models.IntegerField(default=0)
    currency = models.CharField(max_length=3)

    status = models.CharField(max_length=30)  # succeeded, pending, failed
    paid = models.BooleanField(default=False)
    refunded = models.BooleanField(default=False)
    disputed = models.BooleanField(default=False)

    description = models.TextField(blank=True)
    statement_descriptor = models.CharField(max_length=255, blank=True)

    # Customer
    customer_id = models.CharField(max_length=255, blank=True)
    customer_email = models.CharField(max_length=255, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)

    # Payment method
    payment_method_type = models.CharField(max_length=50, blank=True)  # card, sepa_debit, bancontact
    card_brand = models.CharField(max_length=20, blank=True)  # visa, mastercard, amex
    card_last4 = models.CharField(max_length=4, blank=True)
    card_country = models.CharField(max_length=2, blank=True)

    # Invoice link
    invoice_id = models.CharField(max_length=255, blank=True)

    # Stripe-specific
    receipt_url = models.URLField(blank=True)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict)  # Stripe custom metadata
    raw_data = models.JSONField(default=dict)

    created_at_stripe = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_stripe']


class StripePayout(models.Model):
    """Stripe payout — transfer to bank account."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_payouts')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='payouts')
    stripe_id = models.CharField(max_length=255, unique=True)  # po_xxx

    amount = models.IntegerField()  # cents
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)  # paid, pending, in_transit, canceled, failed

    arrival_date = models.DateField(null=True, blank=True)
    method = models.CharField(max_length=20, blank=True)  # standard, instant

    # Bank account
    destination_type = models.CharField(max_length=20, blank=True)  # bank_account, card
    bank_account_last4 = models.CharField(max_length=4, blank=True)

    # Stripe-specific
    automatic = models.BooleanField(default=True)
    failure_code = models.CharField(max_length=100, blank=True)
    failure_message = models.TextField(blank=True)

    raw_data = models.JSONField(default=dict)
    created_at_stripe = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_stripe']


class StripeInvoice(models.Model):
    """Stripe invoice."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_invoices')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='invoices')
    stripe_id = models.CharField(max_length=255, unique=True)  # in_xxx

    number = models.CharField(max_length=100, blank=True)
    status = models.CharField(max_length=30)  # draft, open, paid, void, uncollectible

    amount_due = models.IntegerField(default=0)  # cents
    amount_paid = models.IntegerField(default=0)
    amount_remaining = models.IntegerField(default=0)
    subtotal = models.IntegerField(default=0)  # before tax
    tax = models.IntegerField(null=True, blank=True)  # tax amount
    total = models.IntegerField(default=0)  # after tax
    currency = models.CharField(max_length=3)

    # Customer
    customer_id = models.CharField(max_length=255, blank=True)
    customer_email = models.CharField(max_length=255, blank=True)
    customer_name = models.CharField(max_length=255, blank=True)

    # Dates
    invoice_date = models.DateTimeField(null=True, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    # Stripe-specific
    subscription_id = models.CharField(max_length=255, blank=True)
    hosted_invoice_url = models.URLField(blank=True)
    invoice_pdf = models.URLField(blank=True)

    # Line items
    line_items = models.JSONField(default=list)  # [{description, amount, quantity, period}]

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-invoice_date']


class StripeSubscription(models.Model):
    """Stripe subscription — recurring billing."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_subscriptions')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='subscriptions')
    stripe_id = models.CharField(max_length=255, unique=True)  # sub_xxx

    status = models.CharField(max_length=30)  # active, past_due, canceled, trialing, incomplete

    customer_id = models.CharField(max_length=255, blank=True)
    customer_email = models.CharField(max_length=255, blank=True)

    # Plan details
    plan_amount = models.IntegerField(default=0)  # cents per interval
    plan_currency = models.CharField(max_length=3, blank=True)
    plan_interval = models.CharField(max_length=10, blank=True)  # month, year, week, day
    plan_interval_count = models.IntegerField(default=1)
    plan_product_name = models.CharField(max_length=255, blank=True)

    # Dates
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)
    canceled_at = models.DateTimeField(null=True, blank=True)
    trial_start = models.DateTimeField(null=True, blank=True)
    trial_end = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    created_at_stripe = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_stripe']


class StripeDispute(models.Model):
    """Stripe dispute/chargeback."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='stripe_disputes')
    connection = models.ForeignKey(StripeConnection, on_delete=models.CASCADE, related_name='disputes')
    stripe_id = models.CharField(max_length=255, unique=True)  # dp_xxx

    charge_id = models.CharField(max_length=255)
    amount = models.IntegerField()  # cents
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)  # needs_response, under_review, won, lost
    reason = models.CharField(max_length=100, blank=True)  # fraudulent, duplicate, etc.

    evidence_due_by = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    created_at_stripe = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_stripe']
