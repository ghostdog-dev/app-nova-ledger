from django.conf import settings
from django.db import models


class ShopifyConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shopify_connection')
    store_name = models.CharField(max_length=255)  # myshopify subdomain
    access_token = models.TextField()  # shpat_... — WARNING: encrypt before production
    shop_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'ShopifyConnection({self.user.email}, store={self.store_name})'


class ShopifyOrder(models.Model):
    """Shopify order."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='shopify_orders')
    connection = models.ForeignKey(ShopifyConnection, on_delete=models.CASCADE, related_name='orders')
    shopify_id = models.BigIntegerField(unique=True)
    order_number = models.IntegerField()
    name = models.CharField(max_length=50, blank=True)  # "#1042"

    email = models.CharField(max_length=255, blank=True)

    # Status fields
    financial_status = models.CharField(max_length=30)  # pending/authorized/partially_paid/paid/partially_refunded/refunded/voided
    fulfillment_status = models.CharField(max_length=30, blank=True, null=True)
    status = models.CharField(max_length=20)  # open/closed/cancelled

    # Amounts — Shopify returns decimal strings
    currency = models.CharField(max_length=3)
    subtotal_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Payment info
    payment_gateway = models.CharField(max_length=100, blank=True)
    transaction_id_external = models.CharField(max_length=255, blank=True)  # e.g. Stripe charge ID from meta_data

    # Customer
    customer_name = models.CharField(max_length=255, blank=True)
    customer_email = models.CharField(max_length=255, blank=True)

    # JSON detail fields
    line_items = models.JSONField(default=list)
    shipping_lines = models.JSONField(default=list)
    tax_lines = models.JSONField(default=list)
    refunds = models.JSONField(default=list)

    # Extra
    note = models.TextField(blank=True)
    tags = models.TextField(blank=True)

    # Dates
    created_at_shopify = models.DateTimeField()
    updated_at_shopify = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at_shopify']
        indexes = [models.Index(fields=['user', 'created_at_shopify'])]

    def __str__(self):
        return f'ShopifyOrder({self.name}, {self.total_price} {self.currency}, {self.financial_status})'
