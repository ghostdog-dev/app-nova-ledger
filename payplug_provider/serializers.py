from rest_framework import serializers

from .models import PayPlugConnection, PayPlugPayment, PayPlugRefund


class PayPlugConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPlugConnection
        fields = [
            'id', 'is_live', 'account_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class PayPlugPaymentSerializer(serializers.ModelSerializer):
    amount_decimal = serializers.ReadOnlyField()

    class Meta:
        model = PayPlugPayment
        fields = [
            'id', 'payplug_id', 'amount', 'amount_decimal', 'amount_refunded', 'currency',
            'is_paid', 'is_refunded', 'is_3ds', 'description',
            'card_last4', 'card_brand', 'card_country', 'card_exp_month', 'card_exp_year',
            'billing_email', 'billing_first_name', 'billing_last_name',
            'failure_code', 'failure_message',
            'installment_plan_id', 'metadata',
            'created_at_payplug', 'paid_at',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PayPlugRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = PayPlugRefund
        fields = [
            'id', 'payplug_id', 'payment_id',
            'amount', 'currency',
            'metadata',
            'created_at_payplug', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
