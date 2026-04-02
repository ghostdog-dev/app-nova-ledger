from django.contrib import admin

from .models import BankFileImport, ImportedTransaction


@admin.register(BankFileImport)
class BankFileImportAdmin(admin.ModelAdmin):
    list_display = ['user', 'original_filename', 'file_format', 'transactions_count', 'duplicates_skipped', 'created_at']
    list_filter = ['file_format', 'created_at']
    search_fields = ['original_filename', 'bank_name']
    raw_id_fields = ['user']


@admin.register(ImportedTransaction)
class ImportedTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'amount', 'currency', 'description', 'counterparty', 'transaction_type']
    list_filter = ['currency', 'date']
    search_fields = ['description', 'counterparty', 'reference']
    raw_id_fields = ['user', 'file_import']
