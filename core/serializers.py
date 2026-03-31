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
    company_id = serializers.IntegerField()
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    granularity = serializers.ChoiceField(
        choices=Execution.GRANULARITY_CHOICES, default='invoice_payment',
    )
    included_connections = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list,
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
