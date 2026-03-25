from django.contrib import admin

from .models import Email, Transaction


@admin.register(Email)
class EmailAdmin(admin.ModelAdmin):
    list_display = ('from_address', 'subject', 'provider', 'status', 'date')
    list_filter = ('provider', 'status')
    search_fields = ('from_address', 'subject')
    readonly_fields = ('fetched_at',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('vendor_name', 'type', 'amount', 'currency', 'status', 'transaction_date', 'confidence')
    list_filter = ('type', 'status', 'currency')
    search_fields = ('vendor_name', 'invoice_number', 'order_number')
    readonly_fields = ('processed_at',)
