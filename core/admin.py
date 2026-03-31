from django.contrib import admin

from .models import Company, CompanyMember, Correlation, Execution, ServiceConnection


class CompanyMemberInline(admin.TabularInline):
    model = CompanyMember
    extra = 0


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'plan', 'is_active', 'member_count', 'created_at']
    list_filter = ['plan', 'is_active']
    search_fields = ['name', 'siret']
    inlines = [CompanyMemberInline]


@admin.register(ServiceConnection)
class ServiceConnectionAdmin(admin.ModelAdmin):
    list_display = ['provider_name', 'company', 'service_type', 'status', 'auth_type', 'last_sync']
    list_filter = ['service_type', 'status', 'auth_type']
    search_fields = ['provider_name', 'company__name']


@admin.register(Execution)
class ExecutionAdmin(admin.ModelAdmin):
    list_display = ['public_id', 'company', 'user', 'status', 'granularity', 'date_from', 'date_to']
    list_filter = ['status', 'granularity']
    search_fields = ['company__name']


@admin.register(Correlation)
class CorrelationAdmin(admin.ModelAdmin):
    list_display = ['public_id', 'execution', 'statut', 'score_confiance', 'is_manual', 'created_at']
    list_filter = ['statut', 'is_manual']
