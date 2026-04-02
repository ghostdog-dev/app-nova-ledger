from django.contrib import admin

from .models import ChorusProConnection, ChorusProInvoice


@admin.register(ChorusProConnection)
class ChorusProConnectionAdmin(admin.ModelAdmin):
    list_display = ['user', 'organization_name', 'is_sandbox', 'is_active', 'last_sync', 'created_at']
    list_filter = ['is_active', 'is_sandbox']
    raw_id_fields = ['user']


@admin.register(ChorusProInvoice)
class ChorusProInvoiceAdmin(admin.ModelAdmin):
    list_display = ['chorus_id', 'numero_facture', 'type_facture', 'montant_ttc', 'devise', 'statut', 'date_depot']
    list_filter = ['statut', 'type_facture', 'devise']
    search_fields = ['chorus_id', 'numero_facture', 'fournisseur_name', 'destinataire_name', 'fournisseur_siret', 'destinataire_siret']
    raw_id_fields = ['user', 'connection']
