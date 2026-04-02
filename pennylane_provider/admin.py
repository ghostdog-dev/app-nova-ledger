from django.contrib import admin

from .models import (
    PennylaneConnection,
    PennylaneCustomerInvoice,
    PennylaneSupplierInvoice,
    PennylaneTransaction,
)


@admin.register(PennylaneConnection)
class PennylaneConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(PennylaneCustomerInvoice)
class PennylaneCustomerInvoiceAdmin(admin.ModelAdmin):
    list_display = ['pennylane_id', 'invoice_number', 'customer_name', 'amount', 'currency', 'status', 'date']
    list_filter = ['status', 'currency']
    search_fields = ['pennylane_id', 'invoice_number', 'customer_name']
    raw_id_fields = ['user', 'connection']


@admin.register(PennylaneSupplierInvoice)
class PennylaneSupplierInvoiceAdmin(admin.ModelAdmin):
    list_display = ['pennylane_id', 'invoice_number', 'supplier_name', 'amount', 'currency', 'status', 'date']
    list_filter = ['status', 'currency']
    search_fields = ['pennylane_id', 'invoice_number', 'supplier_name']
    raw_id_fields = ['user', 'connection']


@admin.register(PennylaneTransaction)
class PennylaneTransactionAdmin(admin.ModelAdmin):
    list_display = ['pennylane_id', 'date', 'amount', 'currency', 'label', 'bank_account_name', 'category']
    list_filter = ['currency']
    search_fields = ['pennylane_id', 'label', 'bank_account_name', 'category']
    raw_id_fields = ['user', 'connection']
