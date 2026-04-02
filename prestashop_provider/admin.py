from django.contrib import admin

from .models import PrestaShopConnection, PrestaShopOrder, PrestaShopPayment


@admin.register(PrestaShopConnection)
class PrestaShopConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'shop_name', 'shop_url', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(PrestaShopOrder)
class PrestaShopOrderAdmin(admin.ModelAdmin):
    list_display = ['prestashop_id', 'reference', 'total_paid', 'current_state', 'payment_method', 'date_add']
    list_filter = ['current_state', 'payment_module']
    search_fields = ['prestashop_id', 'reference', 'invoice_number']
    raw_id_fields = ['user', 'connection']


@admin.register(PrestaShopPayment)
class PrestaShopPaymentAdmin(admin.ModelAdmin):
    list_display = ['prestashop_id', 'order_reference', 'amount', 'payment_method', 'date_add']
    list_filter = ['payment_method']
    search_fields = ['prestashop_id', 'order_reference', 'transaction_id']
    raw_id_fields = ['user', 'connection']
