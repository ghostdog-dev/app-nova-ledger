from rest_framework import serializers

from .models import BankFileImport, ImportedTransaction


class BankFileImportSerializer(serializers.ModelSerializer):
    class Meta:
        model = BankFileImport
        fields = [
            'id', 'original_filename', 'file_format', 'file_size',
            'encoding', 'separator', 'column_mapping', 'bank_name',
            'account_id', 'transactions_count', 'duplicates_skipped',
            'created_at',
        ]
        read_only_fields = fields


class ImportedTransactionSerializer(serializers.ModelSerializer):
    import_filename = serializers.CharField(source='file_import.original_filename', read_only=True)

    class Meta:
        model = ImportedTransaction
        fields = [
            'id', 'file_import_id', 'import_filename',
            'date', 'amount', 'currency', 'description',
            'value_date', 'reference', 'counterparty', 'category',
            'balance_after', 'transaction_type',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
