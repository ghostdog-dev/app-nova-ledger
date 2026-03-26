from rest_framework import serializers

from .models import (
    StripeBalanceTransaction,
    StripeCharge,
    StripeConnection,
    StripeDispute,
    StripeInvoice,
    StripePayout,
    StripeSubscription,
)


class StripeConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeConnection
        fields = [
            'id', 'stripe_account_id', 'account_name', 'is_active',
            'last_sync', 'created_at',
        ]
        read_only_fields = fields


class StripeBalanceTransactionSerializer(serializers.ModelSerializer):
    amount_decimal = serializers.FloatField(read_only=True)
    fee_decimal = serializers.FloatField(read_only=True)
    net_decimal = serializers.FloatField(read_only=True)

    class Meta:
        model = StripeBalanceTransaction
        fields = [
            'id', 'stripe_id', 'amount', 'amount_decimal', 'currency',
            'fee', 'fee_decimal', 'net', 'net_decimal',
            'type', 'status', 'description',
            'source_id', 'source_type',
            'created_at_stripe', 'available_on', 'exchange_rate',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class StripeChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeCharge
        fields = [
            'id', 'stripe_id', 'amount', 'amount_captured', 'amount_refunded',
            'currency', 'status', 'paid', 'refunded', 'disputed',
            'description', 'statement_descriptor',
            'customer_id', 'customer_email', 'customer_name',
            'payment_method_type', 'card_brand', 'card_last4', 'card_country',
            'invoice_id', 'receipt_url',
            'failure_code', 'failure_message',
            'metadata', 'raw_data',
            'created_at_stripe', 'fetched_at',
        ]
        read_only_fields = fields


class StripePayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripePayout
        fields = [
            'id', 'stripe_id', 'amount', 'currency', 'status',
            'arrival_date', 'method',
            'destination_type', 'bank_account_last4',
            'automatic', 'failure_code', 'failure_message',
            'raw_data', 'created_at_stripe', 'fetched_at',
        ]
        read_only_fields = fields


class StripeInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeInvoice
        fields = [
            'id', 'stripe_id', 'number', 'status',
            'amount_due', 'amount_paid', 'amount_remaining',
            'subtotal', 'tax', 'total', 'currency',
            'customer_id', 'customer_email', 'customer_name',
            'invoice_date', 'due_date', 'paid_at',
            'subscription_id', 'hosted_invoice_url', 'invoice_pdf',
            'line_items', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class StripeSubscriptionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeSubscription
        fields = [
            'id', 'stripe_id', 'status',
            'customer_id', 'customer_email',
            'plan_amount', 'plan_currency', 'plan_interval',
            'plan_interval_count', 'plan_product_name',
            'current_period_start', 'current_period_end',
            'cancel_at_period_end', 'canceled_at',
            'trial_start', 'trial_end',
            'raw_data', 'created_at_stripe', 'fetched_at',
        ]
        read_only_fields = fields


class StripeDisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = StripeDispute
        fields = [
            'id', 'stripe_id', 'charge_id',
            'amount', 'currency', 'status', 'reason',
            'evidence_due_by',
            'raw_data', 'created_at_stripe', 'fetched_at',
        ]
        read_only_fields = fields
