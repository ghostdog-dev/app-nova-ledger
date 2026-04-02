from rest_framework import serializers

from .models import (
    EvolizConnection,
    EvolizInvoice,
    EvolizPayment,
    EvolizPurchase,
)


class EvolizConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvolizConnection
        fields = [
            'id', 'company_id', 'account_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class EvolizInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvolizInvoice
        fields = [
            'id', 'evoliz_id', 'document_number', 'typedoc', 'status',
            'documentdate', 'duedate',
            'object_label', 'client_name', 'client_id_evoliz',
            'total_vat_exclude', 'total_vat', 'total_vat_include',
            'total_paid', 'net_to_pay', 'currency',
            'items', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class EvolizPurchaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvolizPurchase
        fields = [
            'id', 'evoliz_id', 'document_number', 'status',
            'documentdate', 'duedate',
            'supplier_name', 'supplier_id_evoliz',
            'total_vat_exclude', 'total_vat', 'total_vat_include',
            'total_paid', 'net_to_pay', 'currency',
            'items', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class EvolizPaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = EvolizPayment
        fields = [
            'id', 'evoliz_id', 'paydate', 'amount',
            'label', 'client_name', 'invoice_number', 'invoice_id_evoliz',
            'paytype_label', 'currency',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
