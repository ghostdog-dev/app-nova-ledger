from django.contrib import admin

from .models import (
    SumUpConnection,
    SumUpPayout,
    SumUpTransaction,
)


@admin.register(SumUpConnection)
class SumUpConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'merchant_code', 'merchant_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(SumUpTransaction)
class SumUpTransactionAdmin(admin.ModelAdmin):
    list_display = ['sumup_id', 'amount', 'currency', 'status', 'type', 'payment_type', 'timestamp']
    list_filter = ['status', 'type', 'payment_type', 'currency']
    search_fields = ['sumup_id', 'transaction_code', 'product_summary']
    raw_id_fields = ['user', 'connection']


@admin.register(SumUpPayout)
class SumUpPayoutAdmin(admin.ModelAdmin):
    list_display = ['sumup_id', 'amount', 'currency', 'status', 'type', 'date']
    list_filter = ['status', 'type']
    search_fields = ['sumup_id', 'reference', 'transaction_code']
    raw_id_fields = ['user', 'connection']
