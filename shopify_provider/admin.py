from django.contrib import admin

from .models import ShopifyConnection, ShopifyOrder


@admin.register(ShopifyConnection)
class ShopifyConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'store_name', 'shop_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(ShopifyOrder)
class ShopifyOrderAdmin(admin.ModelAdmin):
    list_display = ['shopify_id', 'name', 'total_price', 'currency', 'financial_status', 'status', 'created_at_shopify']
    list_filter = ['financial_status', 'status', 'currency']
    search_fields = ['shopify_id', 'name', 'customer_name', 'customer_email', 'tags']
    raw_id_fields = ['user', 'connection']
