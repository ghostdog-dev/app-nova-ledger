from django.conf import settings
from django.db import models


class WooCommerceConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='woocommerce_connection')
    shop_url = models.URLField()  # e.g. https://myshop.com
    consumer_key = models.CharField(max_length=255)  # ck_...
    consumer_secret = models.TextField()  # cs_...
    shop_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'WooCommerceConnection({self.user.email}, shop={self.shop_name or self.shop_url})'


class WooCommerceOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('on-hold', 'On hold'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('refunded', 'Refunded'),
        ('failed', 'Failed'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='woocommerce_orders')
    connection = models.ForeignKey(WooCommerceConnection, on_delete=models.CASCADE, related_name='orders')

    woo_id = models.IntegerField(unique=True)
    order_number = models.CharField(max_length=50, blank=True)  # usually same as str(id)
    status = models.CharField(max_length=30)  # pending, processing, on-hold, completed, cancelled, refunded, failed

    currency = models.CharField(max_length=3)
    subtotal_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_price = models.DecimalField(max_digits=12, decimal_places=2)

    payment_method = models.CharField(max_length=100, blank=True)
    payment_method_title = models.CharField(max_length=255, blank=True)
    transaction_id = models.CharField(max_length=255, blank=True)  # e.g. Stripe ch_ ID

    customer_id_woo = models.IntegerField(null=True, blank=True)
    billing_email = models.CharField(max_length=255, blank=True)
    billing_name = models.CharField(max_length=255, blank=True)

    line_items = models.JSONField(default=list)
    tax_lines = models.JSONField(default=list)
    shipping_lines = models.JSONField(default=list)
    coupon_lines = models.JSONField(default=list)
    refunds_summary = models.JSONField(default=list)

    date_created = models.DateTimeField()
    date_paid = models.DateTimeField(null=True, blank=True)
    date_completed = models.DateTimeField(null=True, blank=True)

    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_created']
        indexes = [models.Index(fields=['user', 'date_created'])]

    def __str__(self):
        return f'WooCommerceOrder(#{self.woo_id}, {self.total_price} {self.currency}, {self.status})'
