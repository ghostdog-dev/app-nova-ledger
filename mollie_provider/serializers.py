from rest_framework import serializers

from .models import (
    MollieConnection,
    MollieInvoice,
    MolliePayment,
    MollieRefund,
    MollieSettlement,
)


class MollieConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MollieConnection
        fields = [
            'id', 'organization_id', 'organization_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class MolliePaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = MolliePayment
        fields = [
            'id', 'mollie_id', 'amount', 'currency',
            'settlement_amount', 'settlement_currency',
            'status', 'description', 'method',
            'card_holder', 'card_number', 'card_brand', 'card_country', 'card_security',
            'ideal_consumer_name', 'ideal_consumer_account', 'ideal_consumer_bic',
            'bank_transfer_reference',
            'redirect_url', 'webhook_url',
            'order_id', 'metadata', 'locale', 'country_code',
            'created_at_mollie', 'paid_at', 'expires_at', 'canceled_at', 'failed_at',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class MollieRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = MollieRefund
        fields = [
            'id', 'mollie_id', 'payment_id',
            'amount', 'currency', 'settlement_amount',
            'status', 'description',
            'created_at_mollie', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class MollieSettlementSerializer(serializers.ModelSerializer):
    class Meta:
        model = MollieSettlement
        fields = [
            'id', 'mollie_id', 'amount', 'currency', 'status',
            'periods', 'settled_at', 'created_at_mollie',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class MollieInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = MollieInvoice
        fields = [
            'id', 'mollie_id', 'reference', 'vat_number',
            'gross_amount', 'net_amount', 'vat_amount', 'currency',
            'status', 'issued_at', 'due_at', 'paid_at',
            'pdf_url', 'lines',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
