import uuid

from django.conf import settings
from django.db import models


class Company(models.Model):
    PLAN_CHOICES = [
        ('free', 'Free'),
        ('plan1', 'Plan 1'),
        ('plan2', 'Plan 2'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255)
    siret = models.CharField(max_length=20, blank=True, default='')
    sector = models.CharField(max_length=100, blank=True, default='')
    plan = models.CharField(max_length=20, default='free', choices=PLAN_CHOICES)
    is_active = models.BooleanField(default=True)
    logo_url = models.URLField(blank=True, default='')
    brand_color = models.CharField(max_length=7, blank=True, default='')
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='owned_companies',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = 'companies'

    def __str__(self):
        return self.name

    @property
    def member_count(self):
        return self.members.count()


class CompanyMember(models.Model):
    ROLE_CHOICES = [
        ('owner', 'Owner'),
        ('admin', 'Admin'),
        ('member', 'Member'),
    ]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='company_memberships',
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('company', 'user')

    def __str__(self):
        return f'{self.user} @ {self.company} ({self.role})'


class ServiceConnection(models.Model):
    SERVICE_TYPE_CHOICES = [
        ('invoicing', 'Invoicing'),
        ('payment', 'Payment'),
        ('email', 'Email'),
        ('banking', 'Banking'),
    ]
    STATUS_CHOICES = [
        ('active', 'Active'),
        ('expired', 'Expired'),
        ('error', 'Error'),
        ('pending', 'Pending'),
    ]
    AUTH_TYPE_CHOICES = [
        ('oauth', 'OAuth'),
        ('api_key', 'API Key'),
        ('file_upload', 'File Upload'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='connections')
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES)
    provider_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    auth_type = models.CharField(max_length=20, choices=AUTH_TYPE_CHOICES)
    credentials = models.JSONField(default=dict, blank=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'provider_name')

    def __str__(self):
        return f'{self.provider_name} ({self.company})'


class Execution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('running', 'Running'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    GRANULARITY_CHOICES = [
        ('invoice_payment', 'Invoice / Payment'),
        ('three_way', 'Three-Way'),
        ('line_by_line', 'Line by Line'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='executions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_from = models.DateField()
    date_to = models.DateField()
    granularity = models.CharField(
        max_length=20, choices=GRANULARITY_CHOICES, default='invoice_payment',
    )
    included_connections = models.ManyToManyField(ServiceConnection, blank=True)
    parameters = models.JSONField(default=dict, blank=True)
    summary = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    duration_seconds = models.FloatField(null=True, blank=True)
    date_start = models.DateTimeField(null=True, blank=True)
    date_end = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Execution {self.public_id} ({self.status})'


class Correlation(models.Model):
    STATUT_CHOICES = [
        ('reconciled', 'Reconciled'),
        ('reconciled_with_alert', 'Reconciled with Alert'),
        ('unpaid', 'Unpaid'),
        ('orphan_payment', 'Orphan Payment'),
        ('uncertain', 'Uncertain'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name='correlations')
    invoice_data = models.JSONField(null=True, blank=True)
    payment_data = models.JSONField(null=True, blank=True)
    score_confiance = models.FloatField(default=0)
    statut = models.CharField(max_length=30, choices=STATUT_CHOICES, default='uncertain')
    match_criteria = models.TextField(blank=True, default='')
    is_manual = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Correlation {self.public_id} ({self.statut})'


class Anomaly(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    correlation = models.ForeignKey(
        Correlation, on_delete=models.CASCADE, related_name='anomalies',
        null=True, blank=True,
    )
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name='anomalies')
    type = models.CharField(max_length=50)
    description = models.TextField()
    severity = models.CharField(max_length=20, default='medium')
    invoice_data = models.JSONField(null=True, blank=True)
    payment_data = models.JSONField(null=True, blank=True)
    amount_impact = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    resolution_notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name_plural = 'anomalies'

    def __str__(self):
        return f'{self.type} — {self.severity}'


class ExportFile(models.Model):
    FORMAT_CHOICES = [
        ('csv', 'CSV'),
        ('excel', 'Excel'),
        ('pdf', 'PDF'),
        ('json', 'JSON'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('generating', 'Generating'),
        ('ready', 'Ready'),
        ('error', 'Error'),
        ('expired', 'Expired'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    execution = models.ForeignKey(Execution, on_delete=models.CASCADE, related_name='exports')
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    file_url = models.URLField(blank=True, default='')
    file_size = models.IntegerField(default=0)
    original_filename = models.CharField(max_length=255, blank=True, default='')
    error_message = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'{self.original_filename or self.format} ({self.status})'

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2) if self.file_size else 0
