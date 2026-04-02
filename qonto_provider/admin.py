from django.contrib import admin

from .models import QontoBankAccount, QontoConnection, QontoTransaction


@admin.register(QontoConnection)
class QontoConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(QontoBankAccount)
class QontoBankAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'iban', 'currency', 'balance_cents', 'status', 'is_main', 'fetched_at']
    list_filter = ['status', 'currency', 'is_main']
    search_fields = ['qonto_id', 'name', 'iban', 'slug']
    raw_id_fields = ['user', 'connection']


@admin.register(QontoTransaction)
class QontoTransactionAdmin(admin.ModelAdmin):
    list_display = ['qonto_id', 'amount_cents', 'currency', 'side', 'operation_type', 'status', 'settled_at']
    list_filter = ['status', 'side', 'operation_type', 'currency']
    search_fields = ['qonto_id', 'transaction_id', 'label', 'counterparty_name', 'reference']
    raw_id_fields = ['user', 'connection']
