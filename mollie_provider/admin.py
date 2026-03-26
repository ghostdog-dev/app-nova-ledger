from django.contrib import admin

from .models import (
    MollieConnection,
    MollieInvoice,
    MolliePayment,
    MollieRefund,
    MollieSettlement,
)


@admin.register(MollieConnection)
class MollieConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(MolliePayment)
class MolliePaymentAdmin(admin.ModelAdmin):
    list_display = ['mollie_id', 'amount', 'currency', 'status', 'method', 'created_at_mollie']
    list_filter = ['status', 'method', 'currency']
    search_fields = ['mollie_id', 'description', 'order_id']
    raw_id_fields = ['user', 'connection']


@admin.register(MollieRefund)
class MollieRefundAdmin(admin.ModelAdmin):
    list_display = ['mollie_id', 'payment_id', 'amount', 'currency', 'status', 'created_at_mollie']
    list_filter = ['status']
    search_fields = ['mollie_id', 'payment_id', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(MollieSettlement)
class MollieSettlementAdmin(admin.ModelAdmin):
    list_display = ['mollie_id', 'amount', 'currency', 'status', 'settled_at', 'created_at_mollie']
    list_filter = ['status']
    search_fields = ['mollie_id']
    raw_id_fields = ['user', 'connection']


@admin.register(MollieInvoice)
class MollieInvoiceAdmin(admin.ModelAdmin):
    list_display = ['mollie_id', 'reference', 'gross_amount', 'currency', 'status', 'issued_at']
    list_filter = ['status']
    search_fields = ['mollie_id', 'reference']
    raw_id_fields = ['user', 'connection']
