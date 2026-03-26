from rest_framework import serializers

from .models import BankAccount, BankConnection, BankTransaction


class BankConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankConnection
        fields = [
            'id', 'powens_connection_id', 'bank_name', 'state',
            'last_sync', 'created_at',
        ]
        read_only_fields = fields


class BankAccountSerializer(serializers.ModelSerializer):
    connection_bank_name = serializers.CharField(
        source='connection.bank_name', read_only=True, default=''
    )

    class Meta:
        model = BankAccount
        fields = [
            'id', 'powens_account_id', 'connection_id', 'connection_bank_name',
            'name', 'iban', 'balance', 'currency', 'account_type',
            'disabled', 'last_update',
        ]
        read_only_fields = fields


class BankTransactionSerializer(serializers.ModelSerializer):
    account_name = serializers.CharField(
        source='account.name', read_only=True, default=''
    )
    currency = serializers.CharField(
        source='account.currency', read_only=True, default=''
    )

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'powens_transaction_id', 'account_id', 'account_name',
            'date', 'rdate', 'value', 'currency',
            'original_value', 'original_currency', 'category_id',
            'original_wording', 'simplified_wording',
            'transaction_type', 'coming', 'card',
            'counterparty_label', 'counterparty_iban',
            'raw_data', 'created_at',
        ]
        read_only_fields = fields
