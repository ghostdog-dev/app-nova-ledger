from rest_framework import serializers

from .models import (
    SumUpConnection,
    SumUpPayout,
    SumUpTransaction,
)


class SumUpConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SumUpConnection
        fields = [
            'id', 'merchant_code', 'merchant_name', 'default_currency',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class SumUpTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SumUpTransaction
        fields = [
            'id', 'sumup_id', 'transaction_code',
            'amount', 'vat_amount', 'tip_amount', 'fee_amount', 'refunded_amount',
            'currency', 'timestamp',
            'status', 'type', 'payment_type', 'entry_mode',
            'card_type', 'card_last4',
            'product_summary', 'installments_count',
            'payout_date', 'payout_type', 'auth_code', 'internal_id',
            'products', 'vat_rates', 'metadata',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class SumUpPayoutSerializer(serializers.ModelSerializer):
    class Meta:
        model = SumUpPayout
        fields = [
            'id', 'sumup_id', 'amount', 'currency', 'date',
            'fee', 'status', 'type', 'reference', 'transaction_code',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
