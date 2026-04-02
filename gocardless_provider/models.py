from django.conf import settings
from django.db import models


class GoCardlessConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_connection')
    access_token = models.TextField()  # Bearer token — WARNING: encrypt before production
    environment = models.CharField(max_length=10, default='sandbox')  # 'sandbox' or 'live'
    creditor_id = models.CharField(max_length=255, blank=True)
    creditor_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'GoCardlessConnection({self.user.email}, env={self.environment})'


class GoCardlessPayment(models.Model):
    """GoCardless payment — Direct Debit payment collected from customer."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_payments')
    connection = models.ForeignKey(GoCardlessConnection, on_delete=models.CASCADE, related_name='payments')
    gocardless_id = models.CharField(max_length=255, unique=True)  # PM000xxx

    amount = models.IntegerField()  # in cents/pence
    amount_refunded = models.IntegerField(default=0)
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)
    charge_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)
    scheme = models.CharField(max_length=30, blank=True)  # sepa_core, bacs, ach, etc.
    retry_if_possible = models.BooleanField(default=True)

    mandate_id = models.CharField(max_length=255, blank=True)
    subscription_id = models.CharField(max_length=255, blank=True)
    payout_id = models.CharField(max_length=255, blank=True)

    metadata = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    created_at_gocardless = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_gocardless']

    def __str__(self):
        return f'GoCardlessPayment({self.gocardless_id}, {self.amount} {self.currency}, {self.status})'

    @property
    def amount_decimal(self):
        return self.amount / 100


class GoCardlessMandate(models.Model):
    """GoCardless mandate — authorisation for Direct Debit collection."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_mandates')
    connection = models.ForeignKey(GoCardlessConnection, on_delete=models.CASCADE, related_name='mandates')
    gocardless_id = models.CharField(max_length=255, unique=True)  # MD000xxx

    reference = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=30)
    scheme = models.CharField(max_length=30, blank=True)
    next_possible_charge_date = models.DateField(null=True, blank=True)

    customer_id = models.CharField(max_length=255, blank=True)
    customer_bank_account_id = models.CharField(max_length=255, blank=True)

    metadata = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    created_at_gocardless = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_gocardless']

    def __str__(self):
        return f'GoCardlessMandate({self.gocardless_id}, {self.scheme}, {self.status})'


class GoCardlessSubscription(models.Model):
    """GoCardless subscription — recurring payment schedule."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_subscriptions')
    connection = models.ForeignKey(GoCardlessConnection, on_delete=models.CASCADE, related_name='subscriptions')
    gocardless_id = models.CharField(max_length=255, unique=True)  # SB000xxx

    amount = models.IntegerField()  # in cents/pence
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)
    name = models.CharField(max_length=255, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    interval = models.IntegerField(default=1)
    interval_unit = models.CharField(max_length=10, blank=True)  # weekly, monthly, yearly
    day_of_month = models.IntegerField(null=True, blank=True)

    mandate_id = models.CharField(max_length=255, blank=True)

    upcoming_payments = models.JSONField(default=list)
    metadata = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    created_at_gocardless = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_gocardless']

    def __str__(self):
        return f'GoCardlessSubscription({self.gocardless_id}, {self.amount} {self.currency}, {self.status})'


class GoCardlessPayout(models.Model):
    """GoCardless payout — funds settled to merchant bank account."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_payouts')
    connection = models.ForeignKey(GoCardlessConnection, on_delete=models.CASCADE, related_name='payouts')
    gocardless_id = models.CharField(max_length=255, unique=True)  # PO000xxx

    amount = models.IntegerField()  # in cents/pence
    currency = models.CharField(max_length=3)
    deducted_fees = models.IntegerField(default=0)
    status = models.CharField(max_length=20)
    arrival_date = models.DateField(null=True, blank=True)
    reference = models.CharField(max_length=255, blank=True)
    payout_type = models.CharField(max_length=20, blank=True)  # merchant, partner

    raw_data = models.JSONField(default=dict)
    created_at_gocardless = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_gocardless']

    def __str__(self):
        return f'GoCardlessPayout({self.gocardless_id}, {self.amount} {self.currency}, {self.status})'


class GoCardlessRefund(models.Model):
    """GoCardless refund."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='gocardless_refunds')
    connection = models.ForeignKey(GoCardlessConnection, on_delete=models.CASCADE, related_name='refunds')
    gocardless_id = models.CharField(max_length=255, unique=True)  # RF000xxx

    amount = models.IntegerField()  # in cents/pence
    currency = models.CharField(max_length=3)
    status = models.CharField(max_length=30)
    reference = models.CharField(max_length=255, blank=True)
    payment_id = models.CharField(max_length=255, blank=True)

    metadata = models.JSONField(default=dict)
    raw_data = models.JSONField(default=dict)
    created_at_gocardless = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_gocardless']

    def __str__(self):
        return f'GoCardlessRefund({self.gocardless_id}, {self.amount} {self.currency}, {self.status})'
