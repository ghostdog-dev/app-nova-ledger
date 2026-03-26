from rest_framework import serializers

from .models import Email, Transaction


class EmailSerializer(serializers.ModelSerializer):
    class Meta:
        model = Email
        fields = [
            'id', 'provider', 'message_id', 'from_address', 'from_name',
            'subject', 'snippet', 'date', 'labels', 'has_attachments',
            'status', 'fetched_at',
        ]
        read_only_fields = fields


class TransactionSerializer(serializers.ModelSerializer):
    email_subject = serializers.CharField(source='email.subject', read_only=True, default='')
    email_from = serializers.CharField(source='email.from_address', read_only=True, default='')
    email_has_attachments = serializers.BooleanField(source='email.has_attachments', read_only=True, default=False)
    matched_bank = serializers.SerializerMethodField()
    matched_providers = serializers.SerializerMethodField()

    def get_matched_bank(self, obj):
        try:
            match = obj.bank_matches.select_related('bank_transaction').first()
            if not match or match.status == 'rejected':
                return None
            btx = match.bank_transaction
            return {
                'confidence': match.confidence,
                'method': match.match_method,
                'status': match.status,
                'bank_vendor': btx.simplified_wording or btx.original_wording,
                'bank_amount': str(btx.value),
                'bank_date': str(btx.date),
            }
        except Exception:
            return None

    def get_matched_providers(self, obj):
        try:
            matches = obj.provider_matches.all()
            if not matches:
                return []
            return [{
                'provider': m.provider,
                'provider_transaction_id': m.provider_transaction_id,
                'amount': str(m.provider_amount),
                'currency': m.provider_currency,
                'confidence': m.confidence,
                'method': m.match_method,
                'status': m.status,
            } for m in matches]
        except Exception:
            return []

    class Meta:
        model = Transaction
        fields = [
            'id', 'email_id', 'type', 'status', 'vendor_name', 'amount', 'currency',
            'amount_tax_excl', 'tax_amount', 'tax_rate',
            'payment_method', 'payment_reference', 'items',
            'transaction_date', 'invoice_number', 'order_number',
            'description', 'raw_data', 'confidence', 'processed_at',
            'email_subject', 'email_from', 'email_has_attachments',
            'matched_bank', 'matched_providers',
        ]
        read_only_fields = fields
