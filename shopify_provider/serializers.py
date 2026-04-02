from rest_framework import serializers

from .models import ShopifyConnection, ShopifyOrder


class ShopifyConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopifyConnection
        fields = [
            'id', 'store_name', 'shop_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class ShopifyOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = ShopifyOrder
        fields = [
            'id', 'shopify_id', 'order_number', 'name', 'email',
            'financial_status', 'fulfillment_status', 'status',
            'currency', 'subtotal_price', 'total_tax',
            'total_discounts', 'total_shipping', 'total_price',
            'payment_gateway', 'transaction_id_external',
            'customer_name', 'customer_email',
            'line_items', 'shipping_lines', 'tax_lines', 'refunds',
            'note', 'tags',
            'created_at_shopify', 'updated_at_shopify',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
