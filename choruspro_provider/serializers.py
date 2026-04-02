from rest_framework import serializers

from .models import ChorusProConnection, ChorusProInvoice


class ChorusProConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChorusProConnection
        fields = [
            'id', 'technical_user_id', 'structure_id',
            'is_sandbox', 'organization_name',
            'is_active', 'last_sync', 'created_at',
        ]
        read_only_fields = fields


class ChorusProInvoiceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ChorusProInvoice
        fields = [
            'id', 'chorus_id', 'numero_facture',
            'type_facture', 'statut', 'cadre_facturation',
            'date_depot', 'date_facture', 'date_echeance',
            'montant_ht', 'montant_tva', 'montant_ttc', 'devise',
            'fournisseur_name', 'fournisseur_siret',
            'destinataire_name', 'destinataire_siret',
            'numero_bon_commande', 'numero_engagement',
            'historique_statuts', 'pieces_jointes', 'commentaire',
            'raw_data', 'fetched_at',
        ]
        read_only_fields = fields
