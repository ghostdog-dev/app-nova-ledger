from django.contrib import admin

from .models import (
    VosFacturesClient,
    VosFacturesConnection,
    VosFacturesInvoice,
    VosFacturesPayment,
)


@admin.register(VosFacturesConnection)
class VosFacturesConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_prefix', 'account_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(VosFacturesInvoice)
class VosFacturesInvoiceAdmin(admin.ModelAdmin):
    list_display = ['vosfactures_id', 'number', 'kind', 'status', 'price_gross', 'currency', 'income', 'issue_date']
    list_filter = ['status', 'kind', 'income', 'currency']
    search_fields = ['vosfactures_id', 'number', 'buyer_name', 'seller_name']
    raw_id_fields = ['user', 'connection']


@admin.register(VosFacturesPayment)
class VosFacturesPaymentAdmin(admin.ModelAdmin):
    list_display = ['vosfactures_id', 'price', 'currency', 'provider', 'paid_date', 'invoice_id_vf']
    list_filter = ['provider', 'currency']
    search_fields = ['vosfactures_id', 'invoice_name', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(VosFacturesClient)
class VosFacturesClientAdmin(admin.ModelAdmin):
    list_display = ['vosfactures_id', 'name', 'email', 'city', 'country']
    search_fields = ['vosfactures_id', 'name', 'email', 'tax_no']
    raw_id_fields = ['user', 'connection']
