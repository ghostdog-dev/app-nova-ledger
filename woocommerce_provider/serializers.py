from rest_framework import serializers

from .models import WooCommerceConnection, WooCommerceOrder


class WooCommerceConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = WooCommerceConnection
        fields = [
            'id', 'shop_url', 'shop_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class WooCommerceOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = WooCommerceOrder
        fields = [
            'id', 'woo_id', 'order_number', 'status',
            'currency', 'subtotal_price', 'total_tax',
            'total_shipping', 'total_discount', 'total_price',
            'payment_method', 'payment_method_title', 'transaction_id',
            'customer_id_woo', 'billing_email', 'billing_name',
            'line_items', 'tax_lines', 'shipping_lines',
            'coupon_lines', 'refunds_summary',
            'date_created', 'date_paid', 'date_completed',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
