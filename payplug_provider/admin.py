from django.contrib import admin

from .models import PayPlugConnection, PayPlugPayment, PayPlugRefund


@admin.register(PayPlugConnection)
class PayPlugConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'account_name', 'is_live', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active', 'is_live']
    raw_id_fields = ['user']


@admin.register(PayPlugPayment)
class PayPlugPaymentAdmin(admin.ModelAdmin):
    list_display = ['payplug_id', 'amount', 'currency', 'is_paid', 'is_refunded', 'card_brand', 'created_at_payplug']
    list_filter = ['is_paid', 'is_refunded', 'card_brand', 'currency']
    search_fields = ['payplug_id', 'description', 'billing_email']
    raw_id_fields = ['user', 'connection']


@admin.register(PayPlugRefund)
class PayPlugRefundAdmin(admin.ModelAdmin):
    list_display = ['payplug_id', 'payment_id', 'amount', 'currency', 'created_at_payplug']
    search_fields = ['payplug_id', 'payment_id']
    raw_id_fields = ['user', 'connection']
