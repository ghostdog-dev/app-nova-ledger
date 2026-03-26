from django.contrib import admin

from .models import PayPalConnection, PayPalDispute, PayPalInvoice, PayPalTransaction


@admin.register(PayPalConnection)
class PayPalConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_email', 'is_sandbox', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_sandbox', 'is_active']
    raw_id_fields = ['user']


@admin.register(PayPalTransaction)
class PayPalTransactionAdmin(admin.ModelAdmin):
    list_display = ['paypal_id', 'amount', 'currency', 'transaction_status', 'payer_email', 'initiation_date']
    list_filter = ['transaction_status', 'currency', 'event_code']
    search_fields = ['paypal_id', 'payer_email', 'payer_name', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(PayPalInvoice)
class PayPalInvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'status', 'amount_total', 'currency', 'recipient_email', 'invoice_date']
    list_filter = ['status', 'currency']
    search_fields = ['invoice_number', 'paypal_id', 'recipient_email', 'recipient_name']
    raw_id_fields = ['user', 'connection']


@admin.register(PayPalDispute)
class PayPalDisputeAdmin(admin.ModelAdmin):
    list_display = ['paypal_id', 'reason', 'status', 'dispute_amount', 'currency', 'created_date']
    list_filter = ['status', 'reason']
    search_fields = ['paypal_id', 'disputed_transaction_id']
    raw_id_fields = ['user', 'connection']
