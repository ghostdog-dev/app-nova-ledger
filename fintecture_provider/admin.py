from django.contrib import admin

from .models import (
    FintectureConnection,
    FintecturePayment,
    FintectureSettlement,
)


@admin.register(FintectureConnection)
class FintectureConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_name', 'is_sandbox', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active', 'is_sandbox']
    raw_id_fields = ['user']


@admin.register(FintecturePayment)
class FintecturePaymentAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'amount', 'currency', 'status', 'transfer_state', 'execution_date']
    list_filter = ['status', 'transfer_state', 'currency', 'session_type']
    search_fields = ['session_id', 'communication', 'customer_id']
    raw_id_fields = ['user', 'connection']


@admin.register(FintectureSettlement)
class FintectureSettlementAdmin(admin.ModelAdmin):
    list_display = ['settlement_id', 'amount', 'currency', 'status', 'execution_date']
    list_filter = ['status']
    search_fields = ['settlement_id']
    raw_id_fields = ['user', 'connection']
