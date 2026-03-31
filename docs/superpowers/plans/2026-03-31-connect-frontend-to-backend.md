# Connect React Frontend to Django Backend — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bridge the React frontend (frontend-vite/) to the Django backend by creating the missing API v1 layer, Company model, unified Connections, Dashboard, Executions, and serving the built React app from Django. Remove the old test frontend.

**Architecture:** Create a new Django app `core/` that holds the Company model, unified Connection model, Execution/Correlation/Export models, and all `/api/v1/` endpoints. This app wraps the existing provider apps internally. Django serves the React build via a catch-all view. The frontend `services-catalog.ts` is updated to match the real backend providers.

**Tech Stack:** Django 5.2, DRF, SimpleJWT, React 19, Vite, Zustand, djangorestframework-camel-case

---

## File Structure

### New files to CREATE

```
core/                                  # New Django app — the API v1 layer
├── __init__.py
├── apps.py
├── models.py                          # Company, CompanyMember, ServiceConnection, Execution, Correlation, Anomaly, ExportFile
├── serializers.py                     # DRF serializers for all core models
├── urls.py                            # /api/v1/ URL router
├── views/
│   ├── __init__.py
│   ├── auth.py                        # /accounts/login, register, logout, me, social-login, token/refresh, clear-session
│   ├── companies.py                   # /companies/ CRUD, plan, usage, members
│   ├── connections.py                 # /companies/{pk}/connections/ — unified wrapper over providers
│   ├── dashboard.py                   # /companies/{pk}/dashboard/ — aggregated view
│   ├── executions.py                  # /companies/{pk}/executions/ — orchestrates correlation pipeline
│   ├── correlations.py                # /correlations/ — read/patch
│   ├── exports.py                     # /companies/{pk}/executions/{pk}/exports/ + /exports/{pk}/
│   ├── transactions.py                # /companies/{pk}/transactions/ — unified transaction list
│   └── ws_ticket.py                   # /ws/ticket/ — WebSocket ticket endpoint
├── services/
│   ├── __init__.py
│   ├── provider_registry.py           # Maps provider names to their connect/sync views
│   └── execution_runner.py            # Orchestrates the 6-step execution pipeline
├── admin.py
└── migrations/

frontend/                              # New Django app — serves the React build
├── __init__.py
├── apps.py
├── views.py                           # Catch-all view serving index.html
├── urls.py                            # Catch-all URL pattern
└── templates/
    └── frontend/
        └── index.html                 # Copied from frontend-vite/dist/index.html after build
```

### Files to MODIFY

```
nova_ledger/settings.py                # Add core, frontend, djangorestframework-camel-case
nova_ledger/urls.py                    # Add api/v1/, remove test frontend URLs, add catch-all
requirements.txt                       # Add djangorestframework-camel-case
accounts/models.py                     # No change needed — CustomUser stays as-is
frontend-vite/src/lib/services-catalog.ts  # Update to match real backend providers
frontend-vite/vite.config.ts           # Update build output to ../frontend/static/frontend/
```

### Files to DELETE (test frontend)

```
banking/views_test.py                  # providers_test_page
stripe_financial/templates/stripe_financial/test.html  # Stripe test page
# Remove test view functions from:
accounts/views.py                      # login_page, callback_page, session_login_view
emails/views.py                        # test_page function (keep API views)
```

---

## Task 1: Install djangorestframework-camel-case and configure

**Files:**
- Modify: `requirements.txt`
- Modify: `nova_ledger/settings.py`

The frontend expects camelCase JSON. This package auto-converts snake_case ↔ camelCase.

- [ ] **Step 1: Add dependency**

```
# Add to requirements.txt:
djangorestframework-camel-case>=1.4
```

- [ ] **Step 2: Install**

Run: `pip install djangorestframework-camel-case`

- [ ] **Step 3: Configure in settings.py**

Add to `REST_FRAMEWORK` dict in settings.py:

```python
REST_FRAMEWORK = {
    # ... existing config ...
    'DEFAULT_RENDERER_CLASSES': (
        'djangorestframework_camel_case.render.CamelCaseJSONRenderer',
        'djangorestframework_camel_case.render.CamelCaseBrowsableAPIRenderer',
    ),
    'DEFAULT_PARSER_CLASSES': (
        'djangorestframework_camel_case.parser.CamelCaseFormParser',
        'djangorestframework_camel_case.parser.CamelCaseMultiPartParser',
        'djangorestframework_camel_case.parser.CamelCaseJSONParser',
    ),
}
```

- [ ] **Step 4: Verify existing API still works**

Run: `python manage.py check`
Expected: System check identified no issues.

- [ ] **Step 5: Commit**

```bash
git add requirements.txt nova_ledger/settings.py
git commit -m "chore: add djangorestframework-camel-case for frontend JSON format"
```

---

## Task 2: Create `core` app with Company and CompanyMember models

**Files:**
- Create: `core/__init__.py`, `core/apps.py`, `core/admin.py`
- Create: `core/models.py`
- Modify: `nova_ledger/settings.py` (add to INSTALLED_APPS)

- [ ] **Step 1: Create the app structure**

Run: `python manage.py startapp core`

- [ ] **Step 2: Write the models**

`core/models.py`:

```python
import uuid
from django.conf import settings
from django.db import models


class Company(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=255)
    siret = models.CharField(max_length=20, blank=True, default='')
    sector = models.CharField(max_length=100, blank=True, default='')
    plan = models.CharField(max_length=20, default='free', choices=[
        ('free', 'Free'), ('plan1', 'Plan 1'), ('plan2', 'Plan 2'),
    ])
    is_active = models.BooleanField(default=True)
    logo_url = models.URLField(blank=True, default='')
    brand_color = models.CharField(max_length=7, blank=True, default='')
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='owned_companies')
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
    ROLE_CHOICES = [('owner', 'Owner'), ('admin', 'Admin'), ('member', 'Member')]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='company_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='member')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('company', 'user')

    def __str__(self):
        return f"{self.user.email} - {self.company.name} ({self.role})"
```

- [ ] **Step 3: Add to INSTALLED_APPS in settings.py**

```python
INSTALLED_APPS = [
    # ... existing apps ...
    'core',
]
```

- [ ] **Step 4: Create and run migration**

Run: `python manage.py makemigrations core && python manage.py migrate`

- [ ] **Step 5: Register in admin.py**

`core/admin.py`:
```python
from django.contrib import admin
from .models import Company, CompanyMember

class CompanyMemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0

@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'owner', 'plan', 'is_active', 'created_at')
    inlines = [CompanyMemberInline]
```

- [ ] **Step 6: Commit**

```bash
git add core/ nova_ledger/settings.py
git commit -m "feat(core): add Company and CompanyMember models"
```

---

## Task 3: Add ServiceConnection, Execution, Correlation, Anomaly, ExportFile models

**Files:**
- Modify: `core/models.py`

These models are the unified layer that wraps the per-provider models.

- [ ] **Step 1: Add models to core/models.py**

Append to `core/models.py`:

```python
class ServiceConnection(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'), ('expired', 'Expired'),
        ('error', 'Error'), ('pending', 'Pending'),
    ]
    SERVICE_TYPE_CHOICES = [
        ('invoicing', 'Invoicing'), ('payment', 'Payment'), ('email', 'Email'),
    ]
    AUTH_TYPE_CHOICES = [('oauth', 'OAuth'), ('api_key', 'API Key')]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='connections')
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPE_CHOICES)
    provider_name = models.CharField(max_length=50)  # e.g. 'stripe', 'paypal', 'evoliz'
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    auth_type = models.CharField(max_length=20, choices=AUTH_TYPE_CHOICES)
    credentials = models.JSONField(default=dict, blank=True)  # Encrypted in production
    last_sync = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default='')
    token_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('company', 'provider_name')

    def __str__(self):
        return f"{self.provider_name} ({self.company.name})"


class Execution(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('running', 'Running'),
        ('completed', 'Completed'), ('failed', 'Failed'),
    ]
    GRANULARITY_CHOICES = [
        ('invoice_payment', 'Invoice-Payment'),
        ('three_way', 'Three-Way'),
        ('line_by_line', 'Line by Line'),
    ]

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='executions')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    date_from = models.DateField()
    date_to = models.DateField()
    granularity = models.CharField(max_length=20, choices=GRANULARITY_CHOICES, default='invoice_payment')
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
        return f"Execution {self.public_id} ({self.status})"


class Correlation(models.Model):
    STATUS_CHOICES = [
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
    statut = models.CharField(max_length=30, choices=STATUS_CHOICES, default='uncertain')
    match_criteria = models.TextField(blank=True, default='')
    is_manual = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Correlation {self.public_id} ({self.statut})"


class Anomaly(models.Model):
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    correlation = models.ForeignKey(Correlation, on_delete=models.CASCADE, related_name='anomalies', null=True, blank=True)
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


class ExportFile(models.Model):
    FORMAT_CHOICES = [
        ('csv', 'CSV'), ('excel', 'Excel'), ('pdf', 'PDF'), ('json', 'JSON'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('generating', 'Generating'),
        ('ready', 'Ready'), ('error', 'Error'), ('expired', 'Expired'),
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

    @property
    def file_size_mb(self):
        return round(self.file_size / (1024 * 1024), 2) if self.file_size else 0
```

- [ ] **Step 2: Create and run migration**

Run: `python manage.py makemigrations core && python manage.py migrate`

- [ ] **Step 3: Register in admin**

Add to `core/admin.py`:
```python
from .models import Company, CompanyMember, ServiceConnection, Execution, Correlation, Anomaly, ExportFile

@admin.register(ServiceConnection)
class ServiceConnectionAdmin(admin.ModelAdmin):
    list_display = ('provider_name', 'company', 'status', 'auth_type', 'last_sync')

@admin.register(Execution)
class ExecutionAdmin(admin.ModelAdmin):
    list_display = ('public_id', 'company', 'status', 'date_from', 'date_to', 'created_at')

@admin.register(Correlation)
class CorrelationAdmin(admin.ModelAdmin):
    list_display = ('public_id', 'execution', 'statut', 'score_confiance', 'is_manual')
```

- [ ] **Step 4: Commit**

```bash
git add core/
git commit -m "feat(core): add ServiceConnection, Execution, Correlation, Anomaly, ExportFile models"
```

---

## Task 4: Create core serializers

**Files:**
- Create: `core/serializers.py`

- [ ] **Step 1: Write serializers**

`core/serializers.py`:

```python
from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Company, CompanyMember, ServiceConnection, Execution, Correlation, Anomaly, ExportFile

User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    avatar_url = serializers.SerializerMethodField()
    plan = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ('id', 'email', 'first_name', 'last_name', 'avatar_url', 'plan', 'date_joined')

    def get_avatar_url(self, obj):
        return ''

    def get_plan(self, obj):
        # Return the plan of the user's first company
        company = obj.owned_companies.first()
        return company.plan if company else 'free'


class CompanySerializer(serializers.ModelSerializer):
    owner = UserSerializer(read_only=True)
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Company
        fields = (
            'public_id', 'name', 'siret', 'sector', 'owner', 'plan',
            'is_active', 'logo_url', 'brand_color', 'created_at', 'updated_at', 'member_count',
        )
        read_only_fields = ('public_id', 'owner', 'plan', 'created_at', 'updated_at')


class CompanyMemberSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = CompanyMember
        fields = ('id', 'user', 'role', 'is_active', 'created_at')


class ServiceConnectionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)

    class Meta:
        model = ServiceConnection
        fields = (
            'public_id', 'company', 'company_name', 'service_type', 'provider_name',
            'status', 'auth_type', 'last_sync', 'error_message', 'token_expires_at',
            'created_at', 'updated_at',
        )
        read_only_fields = ('public_id', 'company', 'company_name', 'status', 'last_sync', 'created_at', 'updated_at')


class ExecutionSummarySerializer(serializers.Serializer):
    invoices_processed = serializers.IntegerField()
    correlations_found = serializers.IntegerField()
    anomalies_detected = serializers.IntegerField()
    reconciliation_rate = serializers.FloatField()


class ExecutionSerializer(serializers.ModelSerializer):
    company_name = serializers.CharField(source='company.name', read_only=True)
    user_email = serializers.CharField(source='user.email', read_only=True)

    class Meta:
        model = Execution
        fields = (
            'public_id', 'company', 'company_name', 'user', 'user_email',
            'status', 'date_from', 'date_to', 'date_start', 'date_end',
            'granularity', 'included_connections', 'parameters', 'summary',
            'error_message', 'duration_seconds', 'created_at', 'updated_at',
        )
        read_only_fields = (
            'public_id', 'company', 'company_name', 'user', 'user_email',
            'status', 'date_start', 'date_end', 'summary', 'error_message',
            'duration_seconds', 'created_at', 'updated_at',
        )


class AnomalySerializer(serializers.ModelSerializer):
    class Meta:
        model = Anomaly
        fields = (
            'public_id', 'type', 'description', 'severity',
            'invoice_data', 'payment_data', 'amount_impact',
            'is_resolved', 'resolution_notes', 'created_at',
        )


class CorrelationSerializer(serializers.ModelSerializer):
    invoice = serializers.JSONField(source='invoice_data', read_only=True)
    payment = serializers.JSONField(source='payment_data', read_only=True)
    anomalies = AnomalySerializer(many=True, read_only=True)

    class Meta:
        model = Correlation
        fields = (
            'public_id', 'invoice', 'payment', 'score_confiance',
            'statut', 'match_criteria', 'is_manual', 'notes',
            'anomalies', 'created_at',
        )


class CorrelationUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Correlation
        fields = ('statut', 'notes', 'is_manual')


class ExportFileSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportFile
        fields = (
            'id', 'public_id', 'format', 'status', 'file_url',
            'file_size', 'file_size_mb', 'original_filename',
            'error_message', 'created_at', 'updated_at',
        )


class CreateExecutionSerializer(serializers.Serializer):
    date_from = serializers.DateField()
    date_to = serializers.DateField()
    included_connections = serializers.ListField(child=serializers.CharField())
    granularity = serializers.ChoiceField(choices=['invoice_payment', 'three_way', 'line_by_line'], default='invoice_payment')
    parameters = serializers.DictField(required=False, default=dict)
```

- [ ] **Step 2: Commit**

```bash
git add core/serializers.py
git commit -m "feat(core): add DRF serializers for all core models"
```

---

## Task 5: Create auth views (`/api/v1/accounts/`)

**Files:**
- Create: `core/views/__init__.py`
- Create: `core/views/auth.py`

These wrap dj-rest-auth to match what the frontend expects.

- [ ] **Step 1: Create views directory**

`core/views/__init__.py`:
```python
```

- [ ] **Step 2: Write auth views**

`core/views/auth.py`:

```python
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from core.models import Company, CompanyMember
from core.serializers import UserSerializer

User = get_user_model()


def _build_auth_response(user, request):
    """Build the standard auth response with user data, tokens, and set refresh cookie."""
    refresh = RefreshToken.for_user(user)
    user_data = UserSerializer(user, context={'request': request}).data

    response = Response({
        'user': user_data,
        'tokens': {'access_token': str(refresh.access_token)},
    })

    # Set refresh token as httpOnly cookie
    response.set_cookie(
        key='refresh_token',
        value=str(refresh),
        httponly=True,
        samesite='Lax',
        secure=False,  # Set True in production with HTTPS
        max_age=7 * 24 * 3600,  # 7 days
        path='/',
    )
    return response


def _ensure_company(user):
    """Auto-create a default company for new users if they don't have one."""
    if not Company.objects.filter(owner=user).exists():
        company = Company.objects.create(
            name=f"Entreprise de {user.first_name or user.email}",
            owner=user,
        )
        CompanyMember.objects.create(company=company, user=user, role='owner')


@api_view(['POST'])
@permission_classes([AllowAny])
def login_view(request):
    email = request.data.get('email', '')
    password = request.data.get('password', '')

    try:
        user = User.objects.get(email=email)
    except User.DoesNotExist:
        return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    if not user.check_password(password):
        return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)

    _ensure_company(user)
    return _build_auth_response(user, request)


@api_view(['POST'])
@permission_classes([AllowAny])
def register_view(request):
    email = request.data.get('email', '')
    password = request.data.get('password', '')
    first_name = request.data.get('first_name', '')
    last_name = request.data.get('last_name', '')

    if User.objects.filter(email=email).exists():
        return Response({'email': ['This email is already registered.']}, status=status.HTTP_400_BAD_REQUEST)

    user = User.objects.create_user(
        username=email,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
    )
    _ensure_company(user)
    return _build_auth_response(user, request)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def logout_view(request):
    response = Response(status=status.HTTP_204_NO_CONTENT)
    response.delete_cookie('refresh_token', path='/')
    return response


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def me_view(request):
    if request.method == 'GET':
        return Response(UserSerializer(request.user, context={'request': request}).data)

    # PATCH — update profile
    user = request.user
    for field in ('first_name', 'last_name'):
        if field in request.data:
            setattr(user, field, request.data[field])
    user.save()
    return Response(UserSerializer(user, context={'request': request}).data)


@api_view(['POST'])
@permission_classes([AllowAny])
def token_refresh_view(request):
    refresh_token = request.COOKIES.get('refresh_token')
    if not refresh_token:
        return Response({'detail': 'No refresh token'}, status=status.HTTP_401_UNAUTHORIZED)

    try:
        refresh = RefreshToken(refresh_token)
        return Response({'access': str(refresh.access_token)})
    except Exception:
        return Response({'detail': 'Invalid refresh token'}, status=status.HTTP_401_UNAUTHORIZED)


@api_view(['POST'])
@permission_classes([AllowAny])
def social_login_view(request):
    """Handle social login callback from frontend (Google/Microsoft)."""
    provider = request.data.get('provider')
    code = request.data.get('code')
    redirect_uri = request.data.get('redirect_uri')

    if not all([provider, code]):
        return Response({'detail': 'Missing provider or code'}, status=status.HTTP_400_BAD_REQUEST)

    # Use allauth's adapter to exchange code for user
    from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
    from allauth.socialaccount.providers.microsoft.views import MicrosoftGraphOAuth2Adapter
    from allauth.socialaccount.helpers import complete_social_login
    from allauth.socialaccount.models import SocialLogin, SocialToken, SocialApp, SocialAccount
    import requests as http_requests

    adapter_map = {
        'google': {
            'adapter': GoogleOAuth2Adapter,
            'token_url': 'https://oauth2.googleapis.com/token',
            'userinfo_url': 'https://www.googleapis.com/oauth2/v3/userinfo',
        },
        'microsoft': {
            'adapter': MicrosoftGraphOAuth2Adapter,
            'token_url': 'https://login.microsoftonline.com/common/oauth2/v2.0/token',
            'userinfo_url': 'https://graph.microsoft.com/v1.0/me',
        },
    }

    if provider not in adapter_map:
        return Response({'detail': f'Unknown provider: {provider}'}, status=status.HTTP_400_BAD_REQUEST)

    config = adapter_map[provider]

    try:
        app = SocialApp.objects.get(provider=provider)
    except SocialApp.DoesNotExist:
        return Response({'detail': f'Social app not configured for {provider}'}, status=status.HTTP_400_BAD_REQUEST)

    # Exchange code for tokens
    token_response = http_requests.post(config['token_url'], data={
        'client_id': app.client_id,
        'client_secret': app.secret,
        'code': code,
        'redirect_uri': redirect_uri,
        'grant_type': 'authorization_code',
    })

    if token_response.status_code != 200:
        return Response({'detail': 'Failed to exchange code for token'}, status=status.HTTP_400_BAD_REQUEST)

    token_data = token_response.json()
    access_token = token_data.get('access_token')

    # Get user info
    headers = {'Authorization': f'Bearer {access_token}'}
    userinfo = http_requests.get(config['userinfo_url'], headers=headers).json()

    # Extract email based on provider
    if provider == 'google':
        email = userinfo.get('email', '')
        first_name = userinfo.get('given_name', '')
        last_name = userinfo.get('family_name', '')
        uid = userinfo.get('sub', '')
    else:
        email = userinfo.get('mail') or userinfo.get('userPrincipalName', '')
        first_name = userinfo.get('givenName', '')
        last_name = userinfo.get('surname', '')
        uid = userinfo.get('id', '')

    # Get or create user
    user, created = User.objects.get_or_create(
        email=email,
        defaults={
            'username': email,
            'first_name': first_name,
            'last_name': last_name,
        }
    )

    if created:
        user.set_unusable_password()
        user.save()

    # Store social account link
    SocialAccount.objects.get_or_create(
        user=user, provider=provider,
        defaults={'uid': uid, 'extra_data': userinfo}
    )

    _ensure_company(user)
    return _build_auth_response(user, request)


@api_view(['POST'])
def clear_session_view(request):
    """Clear the refresh cookie (used by frontend when session is invalid)."""
    response = Response(status=status.HTTP_204_NO_CONTENT)
    response.delete_cookie('refresh_token', path='/')
    return response
```

- [ ] **Step 3: Commit**

```bash
git add core/views/
git commit -m "feat(core): add auth views (login, register, logout, me, social-login, token refresh)"
```

---

## Task 6: Create company views (`/api/v1/companies/`)

**Files:**
- Create: `core/views/companies.py`

- [ ] **Step 1: Write company views**

`core/views/companies.py`:

```python
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company, CompanyMember
from core.serializers import CompanySerializer, CompanyMemberSerializer


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def company_list_view(request):
    if request.method == 'GET':
        companies = Company.objects.filter(members__user=request.user, members__is_active=True)
        serializer = CompanySerializer(companies, many=True)
        return Response({'count': len(serializer.data), 'results': serializer.data})

    # POST — create new company
    serializer = CompanySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    company = serializer.save(owner=request.user)
    CompanyMember.objects.create(company=company, user=request.user, role='owner')
    return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def company_detail_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(CompanySerializer(company).data)

    # PATCH
    for field in ('name', 'siret', 'sector'):
        if field in request.data:
            setattr(company, field, request.data[field])
    company.save()
    return Response(CompanySerializer(company).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_plan_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    limits = {
        'free': {'executions_per_month': 5, 'connections': 3, 'members': 1},
        'plan1': {'executions_per_month': 50, 'connections': 15, 'members': 5},
        'plan2': {'executions_per_month': None, 'connections': None, 'members': None},
    }
    plan_display = {'free': 'Gratuit', 'plan1': 'Pro', 'plan2': 'Enterprise'}

    return Response({
        'plan': company.plan,
        'plan_display': plan_display.get(company.plan, company.plan),
        'limits': limits.get(company.plan, {}),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_usage_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    from django.utils import timezone
    now = timezone.now()
    executions_this_month = company.executions.filter(
        created_at__year=now.year, created_at__month=now.month
    ).count()

    limits = {
        'free': {'executions_per_month': 5, 'connections': 3, 'members': 1},
        'plan1': {'executions_per_month': 50, 'connections': 15, 'members': 5},
        'plan2': {'executions_per_month': None, 'connections': None, 'members': None},
    }

    return Response({
        'executions_this_month': executions_this_month,
        'connections': company.connections.count(),
        'members': company.members.count(),
        'limits': limits.get(company.plan, {}),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def company_members_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        members = company.members.select_related('user').all()
        serializer = CompanyMemberSerializer(members, many=True)
        return Response({'count': len(serializer.data), 'results': serializer.data})

    # POST — invite member
    from django.contrib.auth import get_user_model
    User = get_user_model()
    email = request.data.get('email', '')
    role = request.data.get('role', 'member')

    user, _ = User.objects.get_or_create(email=email, defaults={'username': email})
    member, created = CompanyMember.objects.get_or_create(
        company=company, user=user, defaults={'role': role}
    )
    if not created:
        return Response({'detail': 'User is already a member'}, status=status.HTTP_400_BAD_REQUEST)

    return Response(CompanyMemberSerializer(member).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def company_member_detail_view(request, company_pk, member_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        member = company.members.get(pk=member_pk)
    except CompanyMember.DoesNotExist:
        return Response({'detail': 'Member not found'}, status=status.HTTP_404_NOT_FOUND)

    member.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


def _get_company(user, company_pk):
    """Get a company by public_id if user is a member."""
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 2: Commit**

```bash
git add core/views/companies.py
git commit -m "feat(core): add company CRUD, plan, usage, members views"
```

---

## Task 7: Create provider registry and connection views

**Files:**
- Create: `core/services/__init__.py`
- Create: `core/services/provider_registry.py`
- Create: `core/views/connections.py`

The provider registry maps provider names to their existing connect/sync logic.

- [ ] **Step 1: Create provider registry**

`core/services/__init__.py`:
```python
```

`core/services/provider_registry.py`:

```python
"""
Maps frontend provider names to their backend connect/sync implementations.
Each provider entry defines how to connect and sync using the existing provider apps.
"""
from django.utils import timezone


PROVIDER_REGISTRY = {
    # Payment providers
    'stripe': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
        'connect_module': 'stripe_provider.views',
        'connect_class': 'StripeConnectView',
    },
    'paypal': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['client_id', 'client_secret', 'is_sandbox'],
        'connect_module': 'paypal_provider.views',
        'connect_class': 'PayPalConnectView',
    },
    'mollie': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
        'connect_module': 'mollie_provider.views',
        'connect_class': 'MollieConnectView',
    },
    'fintecture': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['app_id', 'app_secret', 'is_sandbox'],
        'connect_module': 'fintecture_provider.views',
        'connect_class': 'FintectureConnectView',
    },
    'gocardless': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['access_token', 'environment'],
        'connect_module': 'gocardless_provider.views',
        'connect_class': 'GoCardlessConnectView',
    },
    'payplug': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['secret_key'],
        'connect_module': 'payplug_provider.views',
        'connect_class': 'PayPlugConnectView',
    },
    'sumup': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key', 'merchant_code'],
        'connect_module': 'sumup_provider.views',
        'connect_class': 'SumUpConnectView',
    },
    # Invoicing providers
    'evoliz': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['public_key', 'secret_key', 'company_id'],
        'connect_module': 'evoliz_provider.views',
        'connect_class': 'EvolizConnectView',
    },
    'pennylane': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['access_token'],
        'connect_module': 'pennylane_provider.views',
        'connect_class': 'PennylaneConnectView',
    },
    'vosfactures': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['api_token', 'account_prefix'],
        'connect_module': 'vosfactures_provider.views',
        'connect_class': 'VosFacturesConnectView',
    },
    'qonto': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['login', 'secret_key'],
        'connect_module': 'qonto_provider.views',
        'connect_class': 'QontoConnectView',
    },
    'choruspro': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['client_id', 'client_secret', 'technical_user_id', 'structure_id', 'is_sandbox'],
        'connect_module': 'choruspro_provider.views',
        'connect_class': 'ChorusProConnectView',
    },
    # E-commerce / enrichment
    'shopify': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['store_name', 'access_token'],
        'connect_module': 'shopify_provider.views',
        'connect_class': 'ShopifyConnectView',
    },
    'prestashop': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['shop_url', 'api_key'],
        'connect_module': 'prestashop_provider.views',
        'connect_class': 'PrestaShopConnectView',
    },
    'woocommerce': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['shop_url', 'consumer_key', 'consumer_secret'],
        'connect_module': 'woocommerce_provider.views',
        'connect_class': 'WooCommerceConnectView',
    },
    'alma': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
        'connect_module': 'alma_provider.views',
        'connect_class': 'AlmaConnectView',
    },
}


def get_provider_config(provider_name):
    """Get provider configuration by name."""
    return PROVIDER_REGISTRY.get(provider_name)


def get_all_providers():
    """Return list of all available providers with their metadata."""
    result = []
    for name, config in PROVIDER_REGISTRY.items():
        result.append({
            'id': name,
            'name': name.replace('_', ' ').title(),
            'service_type': config['service_type'],
            'auth_type': config['auth_type'],
            'credential_fields': config['credential_fields'],
        })
    return result
```

- [ ] **Step 2: Write connection views**

`core/views/connections.py`:

```python
import importlib
from django.test import RequestFactory
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company, ServiceConnection
from core.serializers import ServiceConnectionSerializer
from core.services.provider_registry import get_provider_config, get_all_providers


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def connection_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        connections = company.connections.all()
        serializer = ServiceConnectionSerializer(connections, many=True)
        return Response({'count': len(serializer.data), 'results': serializer.data})

    # POST — connect via API key
    provider_name = request.data.get('provider_name', '')
    service_type = request.data.get('service_type', '')
    auth_type = request.data.get('auth_type', 'api_key')
    credentials = request.data.get('credentials', {})

    provider_config = get_provider_config(provider_name)
    if not provider_config:
        return Response({'detail': f'Unknown provider: {provider_name}'}, status=status.HTTP_400_BAD_REQUEST)

    # Try to connect using the existing provider's connect view
    try:
        module = importlib.import_module(provider_config['connect_module'])
        view_class = getattr(module, provider_config['connect_class'])

        # Build a fake request with the credentials as data
        factory = RequestFactory()
        fake_request = factory.post('/fake/', data=credentials, content_type='application/json')
        fake_request.user = request.user

        view = view_class.as_view()
        provider_response = view(fake_request)

        if provider_response.status_code >= 400:
            return Response(
                {'detail': provider_response.data.get('error', 'Connection failed')},
                status=provider_response.status_code,
            )
    except Exception as e:
        return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    # Create or update the ServiceConnection
    connection, created = ServiceConnection.objects.update_or_create(
        company=company,
        provider_name=provider_name,
        defaults={
            'service_type': service_type or provider_config['service_type'],
            'auth_type': auth_type,
            'credentials': credentials,
            'status': 'active',
            'error_message': '',
        },
    )

    return Response(
        ServiceConnectionSerializer(connection).data,
        status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def connection_check_view(request, company_pk, connection_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        connection = company.connections.get(public_id=connection_pk)
    except ServiceConnection.DoesNotExist:
        return Response({'detail': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    # Try to use the provider's sync to test the connection
    provider_config = get_provider_config(connection.provider_name)
    if not provider_config:
        return Response({'ok': False, 'error': 'Unknown provider'})

    # Simple check: if status is active, it's ok
    return Response({'ok': connection.status == 'active'})


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def connection_delete_view(request, company_pk, connection_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        connection = company.connections.get(public_id=connection_pk)
    except ServiceConnection.DoesNotExist:
        return Response({'detail': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    connection.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_initiate_view(request, company_pk):
    """Start OAuth flow — returns authorization URL for the provider."""
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    provider_name = request.data.get('provider_name', '')
    redirect_uri = request.data.get('redirect_uri', '')

    # For now, OAuth providers are not yet implemented in the backend.
    # Return a placeholder so the frontend flow doesn't break.
    return Response(
        {'detail': f'OAuth not yet configured for {provider_name}'},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def oauth_complete_view(request, company_pk):
    """Complete OAuth flow — exchange code for tokens and create connection."""
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        {'detail': 'OAuth completion not yet configured'},
        status=status.HTTP_501_NOT_IMPLEMENTED,
    )


def _get_company(user, company_pk):
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 3: Commit**

```bash
git add core/services/ core/views/connections.py
git commit -m "feat(core): add provider registry and unified connection views"
```

---

## Task 8: Create dashboard, executions, correlations, exports, transactions views

**Files:**
- Create: `core/views/dashboard.py`
- Create: `core/views/executions.py`
- Create: `core/views/correlations.py`
- Create: `core/views/exports.py`
- Create: `core/views/transactions.py`
- Create: `core/views/ws_ticket.py`

- [ ] **Step 1: Write dashboard view**

`core/views/dashboard.py`:

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company, Execution
from core.serializers import ServiceConnectionSerializer, ExecutionSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def dashboard_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=404)

    connections = company.connections.all()
    last_execution = company.executions.order_by('-created_at').first()

    # Compute stats from the last execution if available
    summary = last_execution.summary if last_execution and last_execution.summary else {}

    total_correlations = 0
    distribution = []
    if last_execution:
        correlations = last_execution.correlations.all()
        total_correlations = correlations.count()
        from django.db.models import Count
        status_counts = correlations.values('statut').annotate(count=Count('id'))
        distribution = [{'status': s['statut'], 'count': s['count']} for s in status_counts]

    stats = {
        'reconciliation_rate': summary.get('reconciliation_rate', 0),
        'total_invoices': summary.get('invoices_processed', 0),
        'anomalies': summary.get('anomalies_detected', 0),
        'connected_services': connections.count(),
    }

    return Response({
        'stats': stats,
        'correlation_distribution': distribution,
        'monthly_evolution': [],  # Populated once we have historical data
        'alerts': _build_alerts(connections),
        'last_execution': ExecutionSerializer(last_execution).data if last_execution else None,
        'recent_transactions': {'transactions': [], 'total_count': 0},
        'connections': ServiceConnectionSerializer(connections, many=True).data,
    })


def _build_alerts(connections):
    alerts = []
    for conn in connections:
        if conn.status == 'error':
            alerts.append({
                'id': str(conn.public_id),
                'type': 'error',
                'title': f'{conn.provider_name} connection error',
                'message': conn.error_message or 'Connection has an error',
                'created_at': conn.updated_at.isoformat(),
            })
        elif conn.status == 'expired':
            alerts.append({
                'id': str(conn.public_id),
                'type': 'warning',
                'title': f'{conn.provider_name} token expired',
                'message': 'Please reconnect this service',
                'created_at': conn.updated_at.isoformat(),
            })
    return alerts


def _get_company(user, company_pk):
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 2: Write executions view**

`core/views/executions.py`:

```python
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company, Execution, ServiceConnection
from core.serializers import ExecutionSerializer, CreateExecutionSerializer


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def execution_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        executions = company.executions.order_by('-created_at')
        serializer = ExecutionSerializer(executions, many=True)
        return Response({'count': len(serializer.data), 'results': serializer.data})

    # POST — create new execution
    ser = CreateExecutionSerializer(data=request.data)
    ser.is_valid(raise_exception=True)

    execution = Execution.objects.create(
        company=company,
        user=request.user,
        date_from=ser.validated_data['date_from'],
        date_to=ser.validated_data['date_to'],
        granularity=ser.validated_data.get('granularity', 'invoice_payment'),
        parameters=ser.validated_data.get('parameters', {}),
        status='pending',
    )

    # Link included connections
    connection_ids = ser.validated_data.get('included_connections', [])
    if connection_ids:
        connections = ServiceConnection.objects.filter(
            company=company, public_id__in=connection_ids
        )
        execution.included_connections.set(connections)

    # TODO: In production, dispatch execution to Celery task
    # For now, run synchronously in a simplified way
    _run_execution_sync(execution)

    return Response(ExecutionSerializer(execution).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def execution_detail_view(request, company_pk, execution_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.get(public_id=execution_pk)
    except Execution.DoesNotExist:
        return Response({'detail': 'Execution not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response(ExecutionSerializer(execution).data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def execution_progress_view(request, company_pk, execution_pk):
    """Polling fallback for execution progress (when WebSocket is unavailable)."""
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.get(public_id=execution_pk)
    except Execution.DoesNotExist:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    if execution.status == 'completed':
        return Response({
            'type': 'completed',
            'summary': execution.summary or {},
        })
    elif execution.status == 'failed':
        return Response({
            'type': 'failed',
            'error': execution.error_message,
        })
    else:
        return Response({
            'type': 'progress',
            'step': 'correlation',
            'step_index': 3,
            'total_steps': 6,
            'percentage': 50,
            'message': f'Execution is {execution.status}',
        })


def _run_execution_sync(execution):
    """Simplified synchronous execution runner using existing AI correlate logic."""
    import time
    start = timezone.now()
    execution.status = 'running'
    execution.date_start = start
    execution.save()

    try:
        # Use the existing AI correlation service
        from banking.services.correlation import correlate_transactions
        from banking.services.enrichment import enrich_transactions

        # Run correlation
        results = correlate_transactions(execution.user)

        # Build summary from results
        bank_stats = results.get('bank_stats', {})
        provider_stats = results.get('provider_stats', {})
        total_matches = bank_stats.get('matched', 0) + provider_stats.get('matched', 0)
        total_items = bank_stats.get('total', 0) + provider_stats.get('total', 0)

        execution.summary = {
            'invoices_processed': total_items,
            'correlations_found': total_matches,
            'anomalies_detected': 0,
            'reconciliation_rate': round(total_matches / max(total_items, 1) * 100, 1),
        }
        execution.status = 'completed'
    except Exception as e:
        execution.status = 'failed'
        execution.error_message = str(e)
    finally:
        execution.date_end = timezone.now()
        execution.duration_seconds = (execution.date_end - start).total_seconds()
        execution.save()


def _get_company(user, company_pk):
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 3: Write correlations view**

`core/views/correlations.py`:

```python
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Correlation
from core.serializers import CorrelationSerializer, CorrelationUpdateSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def correlation_list_view(request):
    execution_id = request.query_params.get('execution')
    if not execution_id:
        return Response({'detail': 'execution query param required'}, status=status.HTTP_400_BAD_REQUEST)

    correlations = Correlation.objects.filter(
        execution__public_id=execution_id,
        execution__company__members__user=request.user,
    ).select_related('execution')

    serializer = CorrelationSerializer(correlations, many=True)
    return Response({'count': len(serializer.data), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def correlation_detail_view(request, correlation_pk):
    try:
        correlation = Correlation.objects.get(
            public_id=correlation_pk,
            execution__company__members__user=request.user,
        )
    except Correlation.DoesNotExist:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    serializer = CorrelationUpdateSerializer(correlation, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    serializer.save()

    return Response(CorrelationSerializer(correlation).data)
```

- [ ] **Step 4: Write exports view**

`core/views/exports.py`:

```python
import csv
import io
import json
from django.http import HttpResponse
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company, Execution, ExportFile
from core.serializers import ExportFileSerializer, CorrelationSerializer


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_export_view(request, company_pk, execution_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.get(public_id=execution_pk)
    except Execution.DoesNotExist:
        return Response({'detail': 'Execution not found'}, status=status.HTTP_404_NOT_FOUND)

    fmt = request.data.get('format', 'csv')

    export = ExportFile.objects.create(
        execution=execution,
        format=fmt,
        status='generating',
        original_filename=f'export-{execution.public_id}.{fmt}',
    )

    # Generate the export synchronously for now
    try:
        _generate_export(export, execution)
        export.status = 'ready'
    except Exception as e:
        export.status = 'error'
        export.error_message = str(e)
    export.save()

    return Response(ExportFileSerializer(export).data, status=status.HTTP_201_CREATED)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_detail_view(request, export_pk):
    try:
        export = ExportFile.objects.get(
            public_id=export_pk,
            execution__company__members__user=request.user,
        )
    except ExportFile.DoesNotExist:
        return Response({'detail': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

    return Response(ExportFileSerializer(export).data)


def _generate_export(export, execution):
    """Simple export generation — stores data as JSON in file_url for now."""
    correlations = execution.correlations.all()
    data = CorrelationSerializer(correlations, many=True).data
    # In production, this would upload to S3/GCS and set file_url
    export.file_url = f'/api/v1/exports/{export.public_id}/download/'
    export.file_size = len(json.dumps(data).encode())


def _get_company(user, company_pk):
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 5: Write transactions view**

`core/views/transactions.py`:

```python
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from core.models import Company


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_list_view(request, company_pk):
    """Unified transaction list across all sources for a company."""
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Not found'}, status=404)

    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 20))

    # Gather transactions from banking module
    from banking.models import BankTransaction
    bank_txs = BankTransaction.objects.filter(
        account__connection__user=request.user
    ).order_by('-date')

    # Convert to unified format
    transactions = []
    for tx in bank_txs[(page - 1) * page_size:page * page_size]:
        transactions.append({
            'date': tx.date.isoformat() if tx.date else '',
            'desc': tx.original_wording or tx.simplified_wording or '',
            'amount': str(tx.value) if tx.value else '0',
            'status': 'matched' if hasattr(tx, 'match') else 'pending',
            'source': 'bank',
        })

    total_count = bank_txs.count()

    return Response({
        'results': transactions,
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total_count + page_size - 1) // page_size),
    })


def _get_company(user, company_pk):
    try:
        return Company.objects.filter(
            public_id=company_pk, members__user=user, members__is_active=True
        ).first()
    except Exception:
        return None
```

- [ ] **Step 6: Write ws_ticket view**

`core/views/ws_ticket.py`:

```python
import secrets
from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ws_ticket_view(request):
    """Issue a single-use, short-lived ticket for WebSocket authentication."""
    ticket = secrets.token_urlsafe(32)
    # Store ticket -> user_id mapping in cache, expires in 30 seconds
    cache.set(f'ws_ticket:{ticket}', request.user.id, timeout=30)
    return Response({'ticket': ticket})
```

- [ ] **Step 7: Commit**

```bash
git add core/views/
git commit -m "feat(core): add dashboard, executions, correlations, exports, transactions, ws_ticket views"
```

---

## Task 9: Create core URL configuration

**Files:**
- Create: `core/urls.py`

- [ ] **Step 1: Write URL config**

`core/urls.py`:

```python
from django.urls import path
from core.views import auth, companies, connections, dashboard, executions, correlations, exports, transactions, ws_ticket

urlpatterns = [
    # Auth
    path('accounts/login/', auth.login_view),
    path('accounts/register/', auth.register_view),
    path('accounts/logout/', auth.logout_view),
    path('accounts/me/', auth.me_view),
    path('accounts/token/refresh/', auth.token_refresh_view),
    path('accounts/social-login/', auth.social_login_view),
    path('accounts/clear-session/', auth.clear_session_view),

    # Companies
    path('companies/', companies.company_list_view),
    path('companies/<uuid:company_pk>/', companies.company_detail_view),
    path('companies/<uuid:company_pk>/plan/', companies.company_plan_view),
    path('companies/<uuid:company_pk>/usage/', companies.company_usage_view),
    path('companies/<uuid:company_pk>/members/', companies.company_members_view),
    path('companies/<uuid:company_pk>/members/<int:member_pk>/', companies.company_member_detail_view),

    # Connections (company-scoped)
    path('companies/<uuid:company_pk>/connections/', connections.connection_list_view),
    path('companies/<uuid:company_pk>/connections/oauth/initiate/', connections.oauth_initiate_view),
    path('companies/<uuid:company_pk>/connections/oauth/complete/', connections.oauth_complete_view),
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/check/', connections.connection_check_view),
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/', connections.connection_delete_view),

    # Dashboard
    path('companies/<uuid:company_pk>/dashboard/', dashboard.dashboard_view),

    # Executions
    path('companies/<uuid:company_pk>/executions/', executions.execution_list_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/', executions.execution_detail_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/progress/', executions.execution_progress_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/exports/', exports.create_export_view),

    # Correlations (top-level)
    path('correlations/', correlations.correlation_list_view),
    path('correlations/<uuid:correlation_pk>/', correlations.correlation_detail_view),

    # Exports
    path('exports/<uuid:export_pk>/', exports.export_detail_view),

    # Transactions
    path('companies/<uuid:company_pk>/transactions/', transactions.transaction_list_view),

    # WebSocket ticket
    path('ws/ticket/', ws_ticket.ws_ticket_view),
]
```

- [ ] **Step 2: Commit**

```bash
git add core/urls.py
git commit -m "feat(core): add API v1 URL configuration"
```

---

## Task 10: Update main urls.py — add api/v1/, remove test frontend, add catch-all

**Files:**
- Modify: `nova_ledger/urls.py`

- [ ] **Step 1: Rewrite urls.py**

Replace `nova_ledger/urls.py` with:

```python
from django.contrib import admin
from django.urls import include, path, re_path

from banking.views import BankCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1 — the unified API for the React frontend
    path('api/v1/', include('core.urls')),

    # Legacy provider APIs — still used internally by core views
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/emails/', include('emails.urls')),
    path('api/banking/', include('banking.urls')),
    path('api/paypal/', include('paypal_provider.urls')),
    path('api/stripe/', include('stripe_provider.urls')),
    path('api/mollie/', include('mollie_provider.urls')),
    path('api/fintecture/', include('fintecture_provider.urls')),
    path('api/gocardless/', include('gocardless_provider.urls')),
    path('api/payplug/', include('payplug_provider.urls')),
    path('api/sumup/', include('sumup_provider.urls')),
    path('api/bank-import/', include('bank_import.urls')),
    path('api/evoliz/', include('evoliz_provider.urls')),
    path('api/pennylane/', include('pennylane_provider.urls')),
    path('api/vosfactures/', include('vosfactures_provider.urls')),
    path('api/qonto/', include('qonto_provider.urls')),
    path('api/shopify/', include('shopify_provider.urls')),
    path('api/prestashop/', include('prestashop_provider.urls')),
    path('api/woocommerce/', include('woocommerce_provider.urls')),
    path('api/alma/', include('alma_provider.urls')),
    path('api/choruspro/', include('choruspro_provider.urls')),
    path('api/ai/', include('ai_agent.urls')),
    path('financial/', include('stripe_financial.urls')),
    path('callback/powens/', BankCallbackView.as_view(), name='powens-callback'),

    # Catch-all: serve React frontend for all non-API routes
    re_path(r'^(?!api/|admin/|financial/|callback/).*$', include('frontend.urls')),
]
```

- [ ] **Step 2: Commit**

```bash
git add nova_ledger/urls.py
git commit -m "feat: add api/v1/ routes, remove test frontend URLs, add catch-all for React"
```

---

## Task 11: Create `frontend` Django app to serve React build

**Files:**
- Create: `frontend/__init__.py`, `frontend/apps.py`, `frontend/views.py`, `frontend/urls.py`
- Modify: `nova_ledger/settings.py`
- Modify: `frontend-vite/vite.config.ts`

- [ ] **Step 1: Create the app**

`frontend/__init__.py`:
```python
```

`frontend/apps.py`:
```python
from django.apps import AppConfig

class FrontendConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'frontend'
```

- [ ] **Step 2: Write the catch-all view**

`frontend/views.py`:
```python
import os
from django.conf import settings
from django.http import HttpResponse, FileResponse
from django.views.decorators.cache import never_cache


@never_cache
def index_view(request):
    """Serve the React app's index.html for all frontend routes."""
    index_path = os.path.join(settings.BASE_DIR, 'frontend', 'templates', 'frontend', 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HttpResponse(f.read(), content_type='text/html')
    return HttpResponse(
        '<h1>Frontend not built</h1><p>Run <code>cd frontend-vite && npm run build</code></p>',
        content_type='text/html',
    )


def static_asset_view(request, path):
    """Serve Vite build assets (JS, CSS, images)."""
    file_path = os.path.join(settings.BASE_DIR, 'frontend', 'static', 'frontend', path)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'))
    from django.http import Http404
    raise Http404
```

- [ ] **Step 3: Write frontend URLs**

`frontend/urls.py`:
```python
from django.urls import path, re_path
from . import views

urlpatterns = [
    path('assets/<path:path>', views.static_asset_view),
    re_path(r'^.*$', views.index_view),
]
```

- [ ] **Step 4: Add to settings.py INSTALLED_APPS**

```python
INSTALLED_APPS = [
    # ... existing ...
    'frontend',
]
```

- [ ] **Step 5: Update vite.config.ts to build into Django's static directory**

```typescript
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  base: '/',
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: 'ws://localhost:8000',
        ws: true,
      },
    },
  },
  build: {
    outDir: path.resolve(__dirname, '../frontend/static/frontend'),
    emptyOutDir: true,
    sourcemap: false,
  },
  css: {
    modules: {
      localsConvention: 'camelCase',
    },
  },
});
```

- [ ] **Step 6: Create a build script that also copies index.html**

Create `scripts/build-frontend.sh`:
```bash
#!/bin/bash
set -e
cd "$(dirname "$0")/../frontend-vite"
npm run build
# Copy index.html to Django templates
mkdir -p ../frontend/templates/frontend
cp ../frontend/static/frontend/index.html ../frontend/templates/frontend/index.html
echo "Frontend built and copied to Django."
```

Run: `chmod +x scripts/build-frontend.sh`

- [ ] **Step 7: Commit**

```bash
git add frontend/ frontend-vite/vite.config.ts scripts/build-frontend.sh nova_ledger/settings.py
git commit -m "feat: add frontend Django app to serve React build from Django"
```

---

## Task 12: Update frontend services-catalog.ts to match real backend providers

**Files:**
- Modify: `frontend-vite/src/lib/services-catalog.ts`

- [ ] **Step 1: Replace with real provider list**

Replace `frontend-vite/src/lib/services-catalog.ts` with:

```typescript
import type { ServiceType } from '@/types';

export type AuthMethod = 'oauth' | 'apikey' | 'both';

export interface ServiceDefinition {
  id: string;
  name: string;
  type: ServiceType;
  authMethod: AuthMethod;
  color: string;
  initials: string;
  description: string;
  credentialFields?: string[];
  apiKeyDocsUrl?: string;
}

export const SERVICES_CATALOG: ServiceDefinition[] = [
  // ── Payment ──────────────────────────────────────────────
  {
    id: 'stripe',
    name: 'Stripe',
    type: 'payment',
    authMethod: 'apikey',
    color: '#635BFF',
    initials: 'ST',
    description: 'Paiements en ligne et abonnements',
    credentialFields: ['api_key'],
    apiKeyDocsUrl: 'https://dashboard.stripe.com/apikeys',
  },
  {
    id: 'paypal',
    name: 'PayPal',
    type: 'payment',
    authMethod: 'apikey',
    color: '#003087',
    initials: 'PP',
    description: 'Paiements en ligne internationaux',
    credentialFields: ['client_id', 'client_secret', 'is_sandbox'],
  },
  {
    id: 'mollie',
    name: 'Mollie',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1E293B',
    initials: 'ML',
    description: 'Paiements multi-methodes',
    credentialFields: ['api_key'],
    apiKeyDocsUrl: 'https://my.mollie.com/dashboard/developers/api-keys',
  },
  {
    id: 'fintecture',
    name: 'Fintecture',
    type: 'payment',
    authMethod: 'apikey',
    color: '#059669',
    initials: 'FT',
    description: 'Paiement instantane Open Banking',
    credentialFields: ['app_id', 'app_secret', 'is_sandbox'],
  },
  {
    id: 'gocardless',
    name: 'GoCardless',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1D4ED8',
    initials: 'GC',
    description: 'Prelevements bancaires (SEPA)',
    credentialFields: ['access_token', 'environment'],
  },
  {
    id: 'payplug',
    name: 'PayPlug',
    type: 'payment',
    authMethod: 'apikey',
    color: '#7C3AED',
    initials: 'PG',
    description: 'Paiements pour les commercants francais',
    credentialFields: ['secret_key'],
  },
  {
    id: 'sumup',
    name: 'SumUp',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1A73E8',
    initials: 'SU',
    description: 'Terminaux de paiement et encaissements',
    credentialFields: ['api_key', 'merchant_code'],
  },
  {
    id: 'qonto',
    name: 'Qonto',
    type: 'payment',
    authMethod: 'apikey',
    color: '#4B32C3',
    initials: 'QT',
    description: 'Compte pro et gestion financiere',
    credentialFields: ['login', 'secret_key'],
  },
  {
    id: 'alma',
    name: 'Alma',
    type: 'payment',
    authMethod: 'apikey',
    color: '#FF6B4A',
    initials: 'AL',
    description: 'Paiement en plusieurs fois',
    credentialFields: ['api_key'],
  },

  // ── Invoicing ────────────────────────────────────────────
  {
    id: 'evoliz',
    name: 'Evoliz',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#16A34A',
    initials: 'EV',
    description: 'Facturation et gestion commerciale',
    credentialFields: ['public_key', 'secret_key', 'company_id'],
    apiKeyDocsUrl: 'https://www.evoliz.io/api-documentation',
  },
  {
    id: 'pennylane',
    name: 'Pennylane',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#8B5CF6',
    initials: 'PL',
    description: 'Comptabilite et facturation',
    credentialFields: ['access_token'],
  },
  {
    id: 'vosfactures',
    name: 'VosFactures',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#F59E0B',
    initials: 'VF',
    description: 'Facturation en ligne',
    credentialFields: ['api_token', 'account_prefix'],
  },
  {
    id: 'choruspro',
    name: 'Chorus Pro',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#0F172A',
    initials: 'CP',
    description: 'Facturation secteur public',
    credentialFields: ['client_id', 'client_secret', 'technical_user_id', 'structure_id', 'is_sandbox'],
  },

  // ── E-commerce (enrichment) ──────────────────────────────
  {
    id: 'shopify',
    name: 'Shopify',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#96BF48',
    initials: 'SH',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['store_name', 'access_token'],
  },
  {
    id: 'prestashop',
    name: 'PrestaShop',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#DF0067',
    initials: 'PS',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['shop_url', 'api_key'],
  },
  {
    id: 'woocommerce',
    name: 'WooCommerce',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#7F54B3',
    initials: 'WC',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['shop_url', 'consumer_key', 'consumer_secret'],
  },
];

export function getServiceById(id: string): ServiceDefinition | undefined {
  return SERVICES_CATALOG.find((s) => s.id === id);
}

export function getServicesByType(type: ServiceType): ServiceDefinition[] {
  return SERVICES_CATALOG.filter((s) => s.type === type);
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend-vite/src/lib/services-catalog.ts
git commit -m "feat(frontend): update services catalog to match real backend providers"
```

---

## Task 13: Update frontend AddConnectionModal to support credential fields

**Files:**
- Modify: `frontend-vite/src/components/connections/add-connection-modal.tsx`

The modal currently only handles a single `api_key` field. It needs to dynamically render credential fields based on the provider's `credentialFields`.

- [ ] **Step 1: Read current file and update to use credentialFields from catalog**

The key change is: when a provider is selected and its `authMethod` is `'apikey'`, render input fields for each item in `credentialFields` instead of just one generic API key input. Pass all collected credentials as a dict to `connectApiKey()`.

- [ ] **Step 2: Commit**

```bash
git add frontend-vite/src/components/connections/add-connection-modal.tsx
git commit -m "feat(frontend): dynamic credential fields in add connection modal"
```

---

## Task 14: Remove test frontend code

**Files:**
- Delete: `banking/views_test.py`
- Modify: `accounts/views.py` — remove `login_page`, `callback_page`, `session_login_view`
- Modify: `emails/views.py` — remove `test_page` function

- [ ] **Step 1: Delete banking/views_test.py**

Run: `rm banking/views_test.py`

- [ ] **Step 2: Clean accounts/views.py**

Remove `login_page`, `callback_page`, `session_login_view` functions. Keep only the imports needed by remaining code (if any API views exist). If the file only contained test views, replace with an empty file:

```python
# accounts/views.py — test frontend views removed, auth is now in core/views/auth.py
```

- [ ] **Step 3: Clean emails/views.py — remove test_page**

Remove the `test_page` function from `emails/views.py`. Keep all API views (EmailSyncView, EmailClassifyView, etc.) intact.

- [ ] **Step 4: Commit**

```bash
git add -A accounts/views.py emails/views.py
git rm banking/views_test.py
git commit -m "chore: remove old test frontend views"
```

---

## Task 15: Build frontend and verify full stack

- [ ] **Step 1: Install frontend dependencies**

Run: `cd frontend-vite && npm install`

- [ ] **Step 2: Build frontend**

Run: `bash scripts/build-frontend.sh`

- [ ] **Step 3: Run Django migrations and check**

Run: `python manage.py makemigrations && python manage.py migrate && python manage.py check`

- [ ] **Step 4: Create a test superuser (if not exists)**

Run: `python manage.py createsuperuser --email admin@test.com --username admin` (set password interactively)

- [ ] **Step 5: Start Django server and test**

Run: `python manage.py runserver`

Verify in browser:
- `http://localhost:8000/` → React landing page loads
- `http://localhost:8000/login` → React login page
- `http://localhost:8000/api/v1/accounts/login/` → API responds (POST with credentials)
- `http://localhost:8000/admin/` → Django admin still works

- [ ] **Step 6: Commit final state**

```bash
git add -A
git commit -m "feat: full frontend-backend integration — React served by Django with API v1"
```

---

## Summary of all endpoints created

| Frontend expects | Backend provides | Status |
|---|---|---|
| `POST /api/v1/accounts/login/` | `core.views.auth.login_view` | Done |
| `POST /api/v1/accounts/register/` | `core.views.auth.register_view` | Done |
| `POST /api/v1/accounts/logout/` | `core.views.auth.logout_view` | Done |
| `GET/PATCH /api/v1/accounts/me/` | `core.views.auth.me_view` | Done |
| `POST /api/v1/accounts/token/refresh/` | `core.views.auth.token_refresh_view` | Done |
| `POST /api/v1/accounts/social-login/` | `core.views.auth.social_login_view` | Done |
| `POST /api/v1/accounts/clear-session/` | `core.views.auth.clear_session_view` | Done |
| `GET/POST /api/v1/companies/` | `core.views.companies.company_list_view` | Done |
| `GET/PATCH /api/v1/companies/{pk}/` | `core.views.companies.company_detail_view` | Done |
| `GET /api/v1/companies/{pk}/plan/` | `core.views.companies.company_plan_view` | Done |
| `GET /api/v1/companies/{pk}/usage/` | `core.views.companies.company_usage_view` | Done |
| `GET/POST /api/v1/companies/{pk}/members/` | `core.views.companies.company_members_view` | Done |
| `DELETE /api/v1/companies/{pk}/members/{id}/` | `core.views.companies.company_member_detail_view` | Done |
| `GET/POST /api/v1/companies/{pk}/connections/` | `core.views.connections.connection_list_view` | Done |
| `POST .../connections/oauth/initiate/` | `core.views.connections.oauth_initiate_view` | Stub (501) |
| `POST .../connections/oauth/complete/` | `core.views.connections.oauth_complete_view` | Stub (501) |
| `POST .../connections/{id}/check/` | `core.views.connections.connection_check_view` | Done |
| `DELETE .../connections/{id}/` | `core.views.connections.connection_delete_view` | Done |
| `GET /api/v1/companies/{pk}/dashboard/` | `core.views.dashboard.dashboard_view` | Done |
| `GET/POST /api/v1/companies/{pk}/executions/` | `core.views.executions.execution_list_view` | Done |
| `GET .../executions/{pk}/` | `core.views.executions.execution_detail_view` | Done |
| `GET .../executions/{pk}/progress/` | `core.views.executions.execution_progress_view` | Done |
| `POST .../executions/{pk}/exports/` | `core.views.exports.create_export_view` | Done |
| `GET /api/v1/correlations/` | `core.views.correlations.correlation_list_view` | Done |
| `PATCH /api/v1/correlations/{pk}/` | `core.views.correlations.correlation_detail_view` | Done |
| `GET /api/v1/exports/{pk}/` | `core.views.exports.export_detail_view` | Done |
| `GET /api/v1/companies/{pk}/transactions/` | `core.views.transactions.transaction_list_view` | Done |
| `POST /api/v1/ws/ticket/` | `core.views.ws_ticket.ws_ticket_view` | Done |
| Chat WebSocket | Not implemented (needs Django Channels) | Future |
| Execution WebSocket | Not implemented (needs Django Channels) | Future |
| `GET /api/v1/billing/plans/` | Not implemented (needs Stripe Billing) | Future |
| `POST /api/v1/billing/checkout-session/` | Not implemented | Future |
