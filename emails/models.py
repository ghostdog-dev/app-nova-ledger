from django.conf import settings
from django.db import models


class Email(models.Model):
    class Provider(models.TextChoices):
        GOOGLE = 'google'
        MICROSOFT = 'microsoft'

    class Status(models.TextChoices):
        NEW = 'new'
        PROCESSED = 'processed'
        IGNORED = 'ignored'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='emails')
    provider = models.CharField(max_length=20, choices=Provider.choices)
    message_id = models.CharField(max_length=255)
    from_address = models.CharField(max_length=255, blank=True)
    from_name = models.CharField(max_length=255, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    snippet = models.TextField(blank=True)
    date = models.DateTimeField()
    labels = models.JSONField(default=list)
    has_attachments = models.BooleanField(default=False)
    has_list_unsubscribe = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'provider', 'message_id')
        ordering = ['-date']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'provider', 'message_id']),
        ]

    def __str__(self):
        return f'{self.from_address}: {self.subject[:50]}'


class Transaction(models.Model):
    class Type(models.TextChoices):
        INVOICE = 'invoice'
        RECEIPT = 'receipt'
        ORDER = 'order'
        PAYMENT = 'payment'
        SHIPPING = 'shipping'
        REFUND = 'refund'
        SUBSCRIPTION = 'subscription'
        OTHER = 'other'

    class Status(models.TextChoices):
        PARTIAL = 'partial'
        COMPLETE = 'complete'

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    email = models.ForeignKey(Email, on_delete=models.SET_NULL, null=True, blank=True, related_name='transactions')
    type = models.CharField(max_length=20, choices=Type.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PARTIAL)
    vendor_name = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default='EUR')
    transaction_date = models.DateField(null=True, blank=True)
    invoice_number = models.CharField(max_length=100, blank=True)
    order_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict)
    confidence = models.FloatField(default=0.0)
    processed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-transaction_date']
        indexes = [
            models.Index(fields=['user', 'status']),
            models.Index(fields=['user', 'type']),
        ]

    def __str__(self):
        return f'{self.vendor_name} — {self.amount} {self.currency}'
