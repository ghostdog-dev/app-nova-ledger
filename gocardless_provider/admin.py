from django.contrib import admin

from .models import (
    GoCardlessConnection,
    GoCardlessMandate,
    GoCardlessPayment,
    GoCardlessPayout,
    GoCardlessRefund,
    GoCardlessSubscription,
)


@admin.register(GoCardlessConnection)
class GoCardlessConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'environment', 'creditor_name', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active', 'environment']
    raw_id_fields = ['user']


@admin.register(GoCardlessPayment)
class GoCardlessPaymentAdmin(admin.ModelAdmin):
    list_display = ['gocardless_id', 'amount', 'currency', 'status', 'scheme', 'charge_date', 'created_at_gocardless']
    list_filter = ['status', 'scheme', 'currency']
    search_fields = ['gocardless_id', 'reference', 'description']
    raw_id_fields = ['user', 'connection']


@admin.register(GoCardlessMandate)
class GoCardlessMandateAdmin(admin.ModelAdmin):
    list_display = ['gocardless_id', 'reference', 'scheme', 'status', 'created_at_gocardless']
    list_filter = ['status', 'scheme']
    search_fields = ['gocardless_id', 'reference', 'customer_id']
    raw_id_fields = ['user', 'connection']


@admin.register(GoCardlessSubscription)
class GoCardlessSubscriptionAdmin(admin.ModelAdmin):
    list_display = ['gocardless_id', 'name', 'amount', 'currency', 'status', 'interval_unit', 'created_at_gocardless']
    list_filter = ['status', 'interval_unit', 'currency']
    search_fields = ['gocardless_id', 'name']
    raw_id_fields = ['user', 'connection']


@admin.register(GoCardlessPayout)
class GoCardlessPayoutAdmin(admin.ModelAdmin):
    list_display = ['gocardless_id', 'amount', 'currency', 'status', 'arrival_date', 'created_at_gocardless']
    list_filter = ['status', 'payout_type']
    search_fields = ['gocardless_id', 'reference']
    raw_id_fields = ['user', 'connection']


@admin.register(GoCardlessRefund)
class GoCardlessRefundAdmin(admin.ModelAdmin):
    list_display = ['gocardless_id', 'payment_id', 'amount', 'currency', 'status', 'created_at_gocardless']
    list_filter = ['status']
    search_fields = ['gocardless_id', 'payment_id', 'reference']
    raw_id_fields = ['user', 'connection']
