from rest_framework import serializers

from .models import PayPalConnection, PayPalDispute, PayPalInvoice, PayPalTransaction


class PayPalConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPalConnection
        fields = [
            'id', 'account_email', 'is_sandbox', 'is_active',
            'last_sync', 'created_at',
        ]
        read_only_fields = fields


class PayPalTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPalTransaction
        fields = [
            'id', 'paypal_id', 'amount', 'currency', 'fee', 'net',
            'event_code', 'transaction_status',
            'description', 'note',
            'payer_email', 'payer_name', 'payer_id',
            'protection_eligibility',
            'invoice_id', 'custom_field',
            'initiation_date', 'updated_date',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PayPalInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPalInvoice
        fields = [
            'id', 'paypal_id', 'invoice_number', 'status',
            'amount_total', 'amount_due', 'currency',
            'merchant_memo', 'terms_and_conditions',
            'recipient_email', 'recipient_name',
            'invoice_date', 'due_date',
            'payments', 'refunds', 'line_items',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PayPalDisputeSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPalDispute
        fields = [
            'id', 'paypal_id', 'disputed_transaction_id',
            'reason', 'status', 'dispute_amount', 'currency',
            'dispute_outcome', 'dispute_life_cycle_stage',
            'created_date', 'updated_date',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
