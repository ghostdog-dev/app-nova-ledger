from rest_framework import serializers

from .models import (
    PennylaneConnection,
    PennylaneCustomerInvoice,
    PennylaneSupplierInvoice,
    PennylaneTransaction,
)


class PennylaneConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PennylaneConnection
        fields = [
            'id', 'account_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class PennylaneCustomerInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PennylaneCustomerInvoice
        fields = [
            'id', 'pennylane_id', 'invoice_number', 'status',
            'date', 'deadline',
            'customer_name', 'customer_id_pennylane',
            'amount', 'currency', 'tax', 'total',
            'paid_amount', 'remaining_amount',
            'line_items', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PennylaneSupplierInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = PennylaneSupplierInvoice
        fields = [
            'id', 'pennylane_id', 'invoice_number', 'status',
            'date', 'deadline',
            'supplier_name', 'supplier_id_pennylane',
            'amount', 'currency', 'tax', 'total',
            'paid_amount', 'remaining_amount',
            'line_items', 'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class PennylaneTransactionSerializer(serializers.ModelSerializer):
    class Meta:
        model = PennylaneTransaction
        fields = [
            'id', 'pennylane_id', 'date',
            'amount', 'currency', 'label',
            'bank_account_name', 'category',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
