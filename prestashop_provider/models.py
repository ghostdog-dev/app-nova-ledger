from django.conf import settings
from django.db import models


class PrestaShopConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prestashop_connection')
    shop_url = models.URLField()  # e.g. https://myshop.com
    api_key = models.TextField()  # WARNING: encrypt before production
    shop_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'PrestaShopConnection({self.user.email}, shop={self.shop_name})'


class PrestaShopOrder(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prestashop_orders')
    connection = models.ForeignKey(PrestaShopConnection, on_delete=models.CASCADE, related_name='orders')
    prestashop_id = models.IntegerField(unique=True)
    reference = models.CharField(max_length=50)
    current_state = models.IntegerField()  # state ID
    current_state_name = models.CharField(max_length=100, blank=True)
    payment_method = models.CharField(max_length=255, blank=True)
    payment_module = models.CharField(max_length=100, blank=True)
    total_paid = models.DecimalField(max_digits=12, decimal_places=2)
    total_paid_real = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_products = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_products_wt = models.DecimalField(max_digits=12, decimal_places=2, default=0)  # TTC
    total_shipping = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_shipping_tax_incl = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_discounts = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency_id = models.IntegerField(null=True, blank=True)
    customer_id_ps = models.IntegerField(null=True, blank=True)
    invoice_number = models.CharField(max_length=50, blank=True)
    line_items = models.JSONField(default=list)  # from associations.order_rows
    date_add = models.DateTimeField()
    date_upd = models.DateTimeField(null=True, blank=True)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_add']
        indexes = [models.Index(fields=['user', 'date_add'])]

    def __str__(self):
        return f'PrestaShopOrder({self.prestashop_id}, ref={self.reference}, {self.total_paid})'


class PrestaShopPayment(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='prestashop_payments')
    connection = models.ForeignKey(PrestaShopConnection, on_delete=models.CASCADE, related_name='payments')
    prestashop_id = models.IntegerField(unique=True)
    order_reference = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=255, blank=True)
    transaction_id = models.CharField(max_length=255, blank=True)
    card_brand = models.CharField(max_length=50, blank=True)
    date_add = models.DateTimeField()
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_add']

    def __str__(self):
        return f'PrestaShopPayment({self.prestashop_id}, ref={self.order_reference}, {self.amount})'
