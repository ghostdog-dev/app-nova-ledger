from rest_framework import serializers

from .models import (
    VosFacturesClient,
    VosFacturesConnection,
    VosFacturesInvoice,
    VosFacturesPayment,
)


class VosFacturesConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = VosFacturesConnection
        fields = [
            'id', 'account_prefix', 'account_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class VosFacturesInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = VosFacturesInvoice
        fields = [
            'id', 'vosfactures_id', 'number', 'kind', 'status',
            'issue_date', 'sell_date', 'payment_to', 'paid_date',
            'price_net', 'price_gross', 'price_tax', 'paid', 'currency',
            'income', 'buyer_name', 'buyer_tax_no', 'client_id_vf',
            'seller_name', 'payment_type', 'positions',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class VosFacturesPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = VosFacturesPayment
        fields = [
            'id', 'vosfactures_id', 'price', 'paid_date', 'currency',
            'invoice_id_vf', 'invoice_name', 'provider', 'description',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class VosFacturesClientSerializer(serializers.ModelSerializer):
    class Meta:
        model = VosFacturesClient
        fields = [
            'id', 'vosfactures_id', 'name', 'tax_no', 'email', 'phone',
            'city', 'street', 'post_code', 'country',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
