from django.contrib import admin

from .models import BankAccount, BankConnection, BankTransaction, PowensUser


@admin.register(PowensUser)
class PowensUserAdmin(admin.ModelAdmin):
    list_display = ['user', 'powens_user_id', 'created_at']
    raw_id_fields = ['user']


@admin.register(BankConnection)
class BankConnectionAdmin(admin.ModelAdmin):
    list_display = ['bank_name', 'user', 'state', 'last_sync', 'created_at']
    list_filter = ['state']
    raw_id_fields = ['user']


@admin.register(BankAccount)
class BankAccountAdmin(admin.ModelAdmin):
    list_display = ['name', 'iban', 'balance', 'currency', 'account_type', 'disabled']
    list_filter = ['currency', 'account_type', 'disabled']
    raw_id_fields = ['user', 'connection']


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ['date', 'original_wording', 'value', 'transaction_type', 'coming']
    list_filter = ['transaction_type', 'coming']
    search_fields = ['original_wording', 'simplified_wording', 'counterparty_label']
    raw_id_fields = ['user', 'account']
