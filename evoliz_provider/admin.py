from django.contrib import admin

from .models import (
    EvolizConnection,
    EvolizInvoice,
    EvolizPayment,
    EvolizPurchase,
)


@admin.register(EvolizConnection)
class EvolizConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'company_id', 'account_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(EvolizInvoice)
class EvolizInvoiceAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'typedoc', 'total_vat_include', 'currency', 'status', 'documentdate']
    list_filter = ['status', 'typedoc', 'currency']
    search_fields = ['document_number', 'client_name', 'object_label']
    raw_id_fields = ['user', 'connection']


@admin.register(EvolizPurchase)
class EvolizPurchaseAdmin(admin.ModelAdmin):
    list_display = ['document_number', 'total_vat_include', 'currency', 'status', 'documentdate']
    list_filter = ['status', 'currency']
    search_fields = ['document_number', 'supplier_name']
    raw_id_fields = ['user', 'connection']


@admin.register(EvolizPayment)
class EvolizPaymentAdmin(admin.ModelAdmin):
    list_display = ['evoliz_id', 'amount', 'currency', 'client_name', 'paydate']
    list_filter = ['currency']
    search_fields = ['label', 'client_name', 'invoice_number']
    raw_id_fields = ['user', 'connection']
