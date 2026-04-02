from rest_framework import serializers

from .models import (
    GoCardlessConnection,
    GoCardlessMandate,
    GoCardlessPayment,
    GoCardlessPayout,
    GoCardlessRefund,
    GoCardlessSubscription,
)


class GoCardlessConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoCardlessConnection
        fields = [
            'id', 'environment', 'creditor_id', 'creditor_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class GoCardlessPaymentSerializer(serializers.ModelSerializer):
    amount_decimal = serializers.ReadOnlyField()

    class Meta:
        model = GoCardlessPayment
        fields = [
            'id', 'gocardless_id', 'amount', 'amount_decimal', 'amount_refunded',
            'currency', 'status', 'charge_date', 'reference', 'description',
            'scheme', 'retry_if_possible',
            'mandate_id', 'subscription_id', 'payout_id',
            'metadata', 'created_at_gocardless',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class GoCardlessMandateSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoCardlessMandate
        fields = [
            'id', 'gocardless_id', 'reference', 'status', 'scheme',
            'next_possible_charge_date',
            'customer_id', 'customer_bank_account_id',
            'metadata', 'created_at_gocardless',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class GoCardlessSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoCardlessSubscription
        fields = [
            'id', 'gocardless_id', 'amount', 'currency', 'status',
            'name', 'start_date', 'end_date',
            'interval', 'interval_unit', 'day_of_month',
            'mandate_id', 'upcoming_payments',
            'metadata', 'created_at_gocardless',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class GoCardlessPayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoCardlessPayout
        fields = [
            'id', 'gocardless_id', 'amount', 'currency',
            'deducted_fees', 'status', 'arrival_date',
            'reference', 'payout_type',
            'created_at_gocardless',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class GoCardlessRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = GoCardlessRefund
        fields = [
            'id', 'gocardless_id', 'amount', 'currency', 'status',
            'reference', 'payment_id',
            'metadata', 'created_at_gocardless',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
