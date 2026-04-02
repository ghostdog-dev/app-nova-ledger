from rest_framework import serializers

from .models import AlmaConnection, AlmaPayment


class AlmaConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlmaConnection
        fields = [
            'id', 'is_sandbox', 'merchant_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class AlmaPaymentSerializer(serializers.ModelSerializer):
    purchase_amount_decimal = serializers.ReadOnlyField()

    class Meta:
        model = AlmaPayment
        fields = [
            'id', 'alma_id', 'state', 'processing_status',
            'purchase_amount', 'purchase_amount_decimal',
            'customer_fee', 'installments_count', 'kind',
            'customer_email', 'customer_name', 'customer_phone',
            'merchant_reference',
            'payment_plan', 'refunds',
            'amount_already_refunded', 'is_completely_refunded',
            'payout_status', 'currency',
            'raw_data', 'created_at_alma', 'fetched_at',
        ]
        read_only_fields = fields
