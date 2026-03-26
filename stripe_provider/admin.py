from django.contrib import admin

from .models import (
    StripeBalanceTransaction,
    StripeCharge,
    StripeConnection,
    StripeDispute,
    StripeInvoice,
    StripePayout,
    StripeSubscription,
)


@admin.register(StripeConnection)
class StripeConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'stripe_account_id', 'account_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active']
    raw_id_fields = ['user']


@admin.register(StripeBalanceTransaction)
class StripeBalanceTransactionAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'type', 'amount', 'currency', 'fee', 'net', 'status', 'created_at_stripe']
    list_filter = ['type', 'status', 'currency']
    search_fields = ['stripe_id', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(StripeCharge)
class StripeChargeAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'amount', 'currency', 'status', 'paid', 'customer_email', 'created_at_stripe']
    list_filter = ['status', 'paid', 'refunded', 'disputed']
    search_fields = ['stripe_id', 'customer_email', 'customer_name', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(StripePayout)
class StripePayoutAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'amount', 'currency', 'status', 'arrival_date', 'method']
    list_filter = ['status', 'method']
    search_fields = ['stripe_id']
    raw_id_fields = ['user', 'connection']


@admin.register(StripeInvoice)
class StripeInvoiceAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'number', 'status', 'total', 'currency', 'customer_email', 'invoice_date']
    list_filter = ['status', 'currency']
    search_fields = ['stripe_id', 'number', 'customer_email', 'customer_name']
    raw_id_fields = ['user', 'connection']


@admin.register(StripeSubscription)
class StripeSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'status', 'plan_product_name', 'plan_amount', 'plan_currency', 'plan_interval']
    list_filter = ['status', 'plan_interval']
    search_fields = ['stripe_id', 'customer_id', 'plan_product_name']
    raw_id_fields = ['user', 'connection']


@admin.register(StripeDispute)
class StripeDisputeAdmin(admin.ModelAdmin):
    list_display = ['stripe_id', 'charge_id', 'amount', 'currency', 'status', 'reason', 'created_at_stripe']
    list_filter = ['status', 'reason']
    search_fields = ['stripe_id', 'charge_id']
    raw_id_fields = ['user', 'connection']
