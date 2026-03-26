from rest_framework import serializers

from .models import BankAccount, BankConnection, BankTransaction, TransactionMatch


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
    account_name = serializers.CharField(source='account.name', read_only=True, default='')
    currency = serializers.CharField(source='account.currency', read_only=True, default='')
    matched_email = serializers.SerializerMethodField()

    def get_matched_email(self, obj):
        try:
            match = obj.match
            if match.status == 'rejected':
                return None
            etx = match.email_transaction
            return {
                'confidence': match.confidence,
                'method': match.match_method,
                'status': match.status,
                'vendor_name': etx.vendor_name,
                'items': etx.items,
                'tax_amount': str(etx.tax_amount) if etx.tax_amount else None,
                'amount_tax_excl': str(etx.amount_tax_excl) if etx.amount_tax_excl else None,
                'invoice_number': etx.invoice_number,
                'order_number': etx.order_number,
                'payment_method': etx.payment_method,
                'description': etx.description,
            }
        except Exception:
            return None

    class Meta:
        model = BankTransaction
        fields = [
            'id', 'powens_transaction_id', 'account_id', 'account_name',
            'date', 'rdate', 'value', 'currency',
            'original_wording', 'simplified_wording',
            'original_value', 'original_currency', 'category_id',
            'transaction_type', 'coming', 'card',
            'counterparty_label', 'counterparty_iban',
            'matched_email',
            'raw_data', 'created_at',
        ]
        read_only_fields = fields


class TransactionMatchSerializer(serializers.ModelSerializer):
    bank_vendor = serializers.CharField(source='bank_transaction.simplified_wording', read_only=True)
    bank_amount = serializers.DecimalField(source='bank_transaction.value', max_digits=12, decimal_places=2, read_only=True)
    email_vendor = serializers.CharField(source='email_transaction.vendor_name', read_only=True)
    email_amount = serializers.DecimalField(source='email_transaction.amount', max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = TransactionMatch
        fields = [
            'id', 'bank_transaction_id', 'email_transaction_id',
            'bank_vendor', 'bank_amount', 'email_vendor', 'email_amount',
            'confidence', 'match_method', 'status', 'matched_at',
        ]
        read_only_fields = fields
