from rest_framework import serializers

from accounts.models import CustomUser

from .models import (
    Anomaly,
    Company,
    CompanyMember,
    Correlation,
    Execution,
    ExportFile,
    ServiceConnection,
)


class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = CustomUser
        fields = ['id', 'email', 'first_name', 'last_name', 'date_joined']
        read_only_fields = fields


class CompanySerializer(serializers.ModelSerializer):
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Company
        fields = [
            'id', 'public_id', 'name', 'siret', 'sector', 'plan',
            'is_active', 'logo_url', 'brand_color', 'owner',
            'member_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'owner', 'member_count', 'created_at', 'updated_at']


class CompanyMemberSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanyMember
        fields = ['id', 'company', 'user', 'role', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class ServiceConnectionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ServiceConnection
        fields = [
            'id', 'public_id', 'company', 'company_name', 'service_type',
            'provider_name', 'status', 'auth_type', 'last_sync',
            'error_message', 'token_expires_at', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at', 'updated_at']


class AnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = Anomaly
        fields = [
            'id', 'public_id', 'correlation', 'execution', 'type',
            'description', 'severity', 'invoice_data', 'payment_data',
            'amount_impact', 'is_resolved', 'resolution_notes', 'created_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at']


class CorrelationSerializer(serializers.ModelSerializer):
    invoice = serializers.JSONField(source='invoice_data', read_only=True)
    payment = serializers.JSONField(source='payment_data', read_only=True)
    anomalies = AnomalySerializer(many=True, read_only=True)

    class Meta:
        model = Correlation
        fields = [
            'id', 'public_id', 'execution', 'invoice_data', 'payment_data',
            'invoice', 'payment', 'score_confiance', 'statut',
            'match_criteria', 'is_manual', 'notes', 'anomalies', 'created_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at']


class CorrelationUpdateSerializer(serializers.Serializer):
    statut = serializers.ChoiceField(
        choices=Correlation.STATUT_CHOICES, required=False,
    )
    notes = serializers.CharField(required=False, allow_blank=True)
    is_manual = serializers.BooleanField(required=False)


class ExecutionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    user_email = serializers.EmailField(source='user.email', read_only=True)

    class Meta:
        model = Execution
        fields = [
            'id', 'public_id', 'company', 'company_name', 'user', 'user_email',
            'status', 'date_from', 'date_to', 'granularity',
            'included_connections', 'parameters', 'summary', 'error_message',
            'duration_seconds', 'date_start', 'date_end',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'id', 'public_id', 'user', 'status', 'summary', 'error_message',
            'duration_seconds', 'date_start', 'date_end', 'created_at', 'updated_at',
        ]


class CreateExecutionSerializer(serializers.Serializer):
    company_id = serializers.IntegerField(required=False, default=0)
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    granularity = serializers.ChoiceField(
        choices=Execution.GRANULARITY_CHOICES, default='invoice_payment',
    )
    included_connections = serializers.ListField(
        child=serializers.CharField(), required=False, default=list,
    )
    parameters = serializers.DictField(required=False, default=dict)


class ExportFileSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.FloatField(read_only=True)

    class Meta:
        model = ExportFile
        fields = [
            'id', 'public_id', 'execution', 'format', 'status',
            'file_url', 'file_size', 'file_size_mb', 'original_filename',
            'error_message', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'public_id', 'created_at', 'updated_at']


# --- Unified Ledger serializers ---

from ai_agent.models import UnifiedTransaction, TransactionCluster


class UnifiedTransactionSerializer(serializers.ModelSerializer):
    reconciliation_status = serializers.SerializerMethodField()

    class Meta:
        model = UnifiedTransaction
        fields = [
            'id', 'public_id', 'source_type', 'source_id', 'evidence_role',
            'direction', 'category', 'amount', 'currency',
            'amount_tax_excl', 'tax_amount', 'tax_rate',
            'transaction_date', 'vendor_name', 'vendor_name_normalized',
            'description', 'reference', 'payment_method', 'items',
            'confidence', 'completeness',
            'pcg_code', 'pcg_label', 'business_personal', 'tva_deductible',
            'cluster', 'created_at',
        ]

    def get_reconciliation_status(self, obj):
        if not obj.cluster_id:
            return 'orphan'
        if obj.cluster and obj.cluster.is_complete:
            return 'matched'
        return 'pending'


class TransactionClusterSerializer(serializers.ModelSerializer):
    transactions = UnifiedTransactionSerializer(many=True, read_only=True)
    transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = TransactionCluster
        fields = [
            'id', 'public_id', 'label', 'cluster_type',
            'total_revenue', 'total_cost', 'margin',
            'total_tax_collected', 'total_tax_deductible',
            'confidence', 'is_complete', 'corroboration_score',
            'verification_status', 'match_reasoning', 'evidence_summary',
            'created_by', 'transactions', 'transactions_count',
            'created_at', 'updated_at',
        ]

    def get_transactions_count(self, obj):
        return obj.transactions.count()


class TransactionClusterListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views (no nested transactions)."""
    transactions_count = serializers.SerializerMethodField()

    class Meta:
        model = TransactionCluster
        fields = [
            'id', 'public_id', 'label', 'cluster_type',
            'total_revenue', 'total_cost', 'margin',
            'confidence', 'is_complete', 'corroboration_score',
            'verification_status', 'transactions_count',
            'created_at',
        ]

    def get_transactions_count(self, obj):
        return obj.transactions.count()
