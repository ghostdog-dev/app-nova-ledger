from rest_framework import serializers

from .models import QontoBankAccount, QontoConnection, QontoTransaction


class QontoConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = QontoConnection
        fields = [
            'id', 'login', 'organization_name', 'iban',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class QontoBankAccountSerializer(serializers.ModelSerializer):
    balance = serializers.FloatField(read_only=True)

    class Meta:
        model = QontoBankAccount
        fields = [
            'id', 'qonto_id', 'slug', 'name', 'iban', 'bic',
            'currency', 'balance_cents', 'balance',
            'authorized_balance_cents', 'status', 'is_main',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields


class QontoTransactionSerializer(serializers.ModelSerializer):
    amount = serializers.FloatField(read_only=True)

    class Meta:
        model = QontoTransaction
        fields = [
            'id', 'qonto_id', 'transaction_id',
            'amount_cents', 'amount', 'currency',
            'side', 'operation_type', 'status',
            'label', 'counterparty_name', 'reference', 'note',
            'settled_at', 'emitted_at', 'category',
            'attachment_ids', 'label_ids',
            'card_last_digits', 'bank_account_id',
            'raw_data', 'created_at_qonto', 'updated_at_qonto', 'fetched_at',
        ]
        read_only_fields = fields
