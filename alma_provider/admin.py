from django.contrib import admin

from .models import AlmaConnection, AlmaPayment


@admin.register(AlmaConnection)
class AlmaConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'merchant_name', 'is_sandbox', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active', 'is_sandbox']
    raw_id_fields = ['user']


@admin.register(AlmaPayment)
class AlmaPaymentAdmin(admin.ModelAdmin):
    list_display = ['alma_id', 'purchase_amount', 'currency', 'state', 'kind', 'installments_count', 'created_at_alma']
    list_filter = ['state', 'kind', 'currency']
    search_fields = ['alma_id', 'customer_email', 'customer_name', 'merchant_reference']
    raw_id_fields = ['user', 'connection']
