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

    class Meta:
        model = Transaction
        fields = [
            'id', 'type', 'status', 'vendor_name', 'amount', 'currency',
            'transaction_date', 'invoice_number', 'order_number',
            'description', 'raw_data', 'confidence', 'processed_at',
            'email_subject', 'email_from',
        ]
        read_only_fields = fields
