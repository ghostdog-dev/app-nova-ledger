from rest_framework import serializers

from .models import (
    FintectureConnection,
    FintecturePayment,
    FintectureSettlement,
)


class FintectureConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FintectureConnection
        fields = [
            'id', 'is_sandbox', 'account_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class FintecturePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = FintecturePayment
        fields = [
            'id', 'session_id', 'amount', 'currency',
            'communication', 'end_to_end_id',
            'execution_date', 'payment_scheme', 'transfer_state',
            'status', 'session_type', 'provider',
            'customer_id', 'bank_account_id',
            'is_accepted', 'has_settlement_completed',
            'metadata', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class FintectureSettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = FintectureSettlement
        fields = [
            'id', 'settlement_id', 'amount', 'currency',
            'status', 'execution_date',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
