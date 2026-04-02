from django.contrib import admin

from .models import WooCommerceConnection, WooCommerceOrder


@admin.register(WooCommerceConnection)
class WooCommerceConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'shop_url', 'shop_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(WooCommerceOrder)
class WooCommerceOrderAdmin(admin.ModelAdmin):
    list_display = ['woo_id', 'order_number', 'total_price', 'currency', 'status', 'payment_method', 'date_created']
    list_filter = ['status', 'payment_method', 'currency']
    search_fields = ['woo_id', 'order_number', 'billing_email', 'billing_name', 'transaction_id']
    raw_id_fields = ['user', 'connection']
