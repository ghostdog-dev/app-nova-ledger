from django.conf import settings
from django.db import models


class ChorusProConnection(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='choruspro_connection')
    client_id = models.CharField(max_length=255)
    client_secret = models.TextField()  # WARNING: encrypt before production
    technical_user_id = models.IntegerField()
    structure_id = models.IntegerField()
    is_sandbox = models.BooleanField(default=True)
    organization_name = models.CharField(max_length=255, blank=True)
    is_active = models.BooleanField(default=True)
    last_sync = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        env = 'sandbox' if self.is_sandbox else 'production'
        return f'ChorusProConnection({self.user.email}, {env}, structure={self.structure_id})'


class ChorusProInvoice(models.Model):
    """Chorus Pro invoice -- sent or received via the French public invoicing portal."""
    TYPE_CHOICES = [
        ('FACTURE', 'Facture'),
        ('AVOIR', 'Avoir'),
        ('ACOMPTE', 'Acompte'),
    ]
    STATUT_CHOICES = [
        ('DEPOSEE', 'Deposee'),
        ('CORRECTE', 'Correcte'),
        ('INCORRECTE', 'Incorrecte'),
        ('MISE_A_DISPOSITION_DESTINATAIRE', 'Mise a disposition destinataire'),
        ('PRISE_EN_CHARGE', 'Prise en charge'),
        ('SUSPENDUE', 'Suspendue'),
        ('A_RECYCLER', 'A recycler'),
        ('REJETEE', 'Rejetee'),
        ('MANDATEE', 'Mandatee'),
        ('MISE_EN_PAIEMENT', 'Mise en paiement'),
        ('COMPLETEE', 'Completee'),
        ('SERVICE_FAIT', 'Service fait'),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='choruspro_invoices')
    connection = models.ForeignKey(ChorusProConnection, on_delete=models.CASCADE, related_name='invoices')
    chorus_id = models.IntegerField(unique=True)  # idFacture
    numero_facture = models.CharField(max_length=255)
    type_facture = models.CharField(max_length=30, choices=TYPE_CHOICES)
    statut = models.CharField(max_length=50, choices=STATUT_CHOICES)
    cadre_facturation = models.CharField(max_length=100, blank=True)
    date_depot = models.DateTimeField(null=True, blank=True)
    date_facture = models.DateField(null=True, blank=True)
    date_echeance = models.DateField(null=True, blank=True)
    montant_ht = models.DecimalField(max_digits=12, decimal_places=2)
    montant_tva = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    montant_ttc = models.DecimalField(max_digits=12, decimal_places=2)
    devise = models.CharField(max_length=3, default='EUR')
    fournisseur_name = models.CharField(max_length=255, blank=True)
    fournisseur_siret = models.CharField(max_length=14, blank=True)
    destinataire_name = models.CharField(max_length=255, blank=True)
    destinataire_siret = models.CharField(max_length=14, blank=True)
    numero_bon_commande = models.CharField(max_length=255, blank=True)
    numero_engagement = models.CharField(max_length=255, blank=True)
    historique_statuts = models.JSONField(default=list)
    pieces_jointes = models.JSONField(default=list)
    commentaire = models.TextField(blank=True)
    raw_data = models.JSONField(default=dict)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date_depot']
        indexes = [models.Index(fields=['user', 'date_depot'])]

    def __str__(self):
        return f'ChorusProInvoice({self.chorus_id}, {self.numero_facture}, {self.montant_ttc} {self.devise}, {self.statut})'
