from rest_framework import serializers

from .models import PrestaShopConnection, PrestaShopOrder, PrestaShopPayment


class PrestaShopConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrestaShopConnection
        fields = [
            'id', 'shop_url', 'shop_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class PrestaShopOrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrestaShopOrder
        fields = [
            'id', 'prestashop_id', 'reference',
            'current_state', 'current_state_name',
            'payment_method', 'payment_module',
            'total_paid', 'total_paid_real',
            'total_products', 'total_products_wt',
            'total_shipping', 'total_shipping_tax_incl',
            'total_discounts',
            'currency_id', 'customer_id_ps', 'invoice_number',
            'line_items',
            'date_add', 'date_upd',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PrestaShopPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrestaShopPayment
        fields = [
            'id', 'prestashop_id', 'order_reference',
            'amount', 'payment_method',
            'transaction_id', 'card_brand',
            'date_add',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
