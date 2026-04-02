import logging
import time
from datetime import date, datetime
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import ChorusProConnection, ChorusProInvoice

logger = logging.getLogger(__name__)

SANDBOX_OAUTH_URL = 'https://sandbox-oauth.aife.economie.gouv.fr/api/oauth/token'
PRODUCTION_OAUTH_URL = 'https://oauth.aife.economie.gouv.fr/api/oauth/token'
SANDBOX_API_BASE = 'https://sandbox-api.aife.economie.gouv.fr'
PRODUCTION_API_BASE = 'https://api.aife.economie.gouv.fr'


class ChorusProClient:
    """Thin wrapper around the Chorus Pro API using httpx."""

    def __init__(self, client_id: str, client_secret: str, technical_user_id: int,
                 structure_id: int, is_sandbox: bool = True):
        self.client_id = client_id
        self.client_secret = client_secret
        self.technical_user_id = technical_user_id
        self.structure_id = structure_id
        self.is_sandbox = is_sandbox

        self.oauth_url = SANDBOX_OAUTH_URL if is_sandbox else PRODUCTION_OAUTH_URL
        api_base = SANDBOX_API_BASE if is_sandbox else PRODUCTION_API_BASE

        self._token: str | None = None
        self._token_expires_at: float = 0

        self.client = httpx.Client(
            base_url=api_base,
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _get_token(self) -> str:
        """Get a valid OAuth token, refreshing if expired."""
        if self._token and time.time() < self._token_expires_at:
            return self._token

        resp = httpx.post(
            self.oauth_url,
            data={
                'grant_type': 'client_credentials',
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'scope': 'openid',
            },
            headers={'Content-Type': 'application/x-www-form-urlencoded'},
            timeout=30.0,
        )
        resp.raise_for_status()
        data = resp.json()

        self._token = data['access_token']
        # Expire 60s early to avoid edge cases
        expires_in = data.get('expires_in', 3600)
        self._token_expires_at = time.time() + expires_in - 60

        return self._token

    def _post(self, endpoint: str, body: dict) -> dict:
        """Make an authenticated POST request to the Chorus Pro API."""
        token = self._get_token()
        resp = self.client.post(
            endpoint,
            json=body,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type': 'application/json',
            },
        )
        resp.raise_for_status()
        data = resp.json()

        # Chorus Pro returns codeRetour=0 on success
        code_retour = data.get('codeRetour')
        if code_retour is not None and code_retour != 0:
            libelle = data.get('libelleRetour', 'Unknown error')
            raise ValueError(f'Chorus Pro API error (code={code_retour}): {libelle}')

        return data

    def search_invoices_sent(self, date_depot_debut: str | None = None,
                             date_depot_fin: str | None = None) -> list[dict]:
        """Search invoices sent (fournisseur). Returns list of invoice summaries."""
        return self._search_invoices(
            '/cpro/factures/v1/rechercher/fournisseur',
            date_depot_debut, date_depot_fin,
        )

    def search_invoices_received(self, date_depot_debut: str | None = None,
                                 date_depot_fin: str | None = None) -> list[dict]:
        """Search invoices received (destinataire). Returns list of invoice summaries."""
        return self._search_invoices(
            '/cpro/factures/v1/rechercher/destinataire',
            date_depot_debut, date_depot_fin,
        )

    def _search_invoices(self, endpoint: str, date_depot_debut: str | None,
                         date_depot_fin: str | None) -> list[dict]:
        """Paginate through invoice search results."""
        results = []
        page = 1

        while True:
            body: dict = {
                'idUtilisateurCourant': self.technical_user_id,
                'idStructure': self.structure_id,
                'pageResultat': page,
                'nbResultatsParPage': 500,
            }

            criteres: dict = {}
            if date_depot_debut:
                criteres['dateDepotDebut'] = date_depot_debut
            if date_depot_fin:
                criteres['dateDepotFin'] = date_depot_fin
            if criteres:
                body['listeCritereRecherche'] = criteres

            data = self._post(endpoint, body)

            factures = data.get('listeFactures', [])
            results.extend(factures)

            total = data.get('total', 0)
            if page * 500 >= total:
                break
            page += 1

        return results

    def get_invoice_detail(self, id_facture: int) -> dict:
        """Get full invoice detail by idFacture."""
        body = {
            'idUtilisateurCourant': self.technical_user_id,
            'idFacture': id_facture,
        }
        return self._post('/cpro/factures/v1/consulter', body)


def _parse_date(value: str | None) -> date | None:
    """Parse YYYY-MM-DD date string from Chorus Pro."""
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except (ValueError, TypeError):
        return None


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from Chorus Pro."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def sync_choruspro_data(user, date_from: str | None = None, date_to: str | None = None) -> dict:
    """Sync all Chorus Pro invoices for a user. Returns stats dict."""
    try:
        connection = user.choruspro_connection
    except ChorusProConnection.DoesNotExist:
        raise ValueError('No Chorus Pro connection found for this user')

    if not connection.is_active:
        raise ValueError('Chorus Pro connection is inactive')

    client = ChorusProClient(
        client_id=connection.client_id,
        client_secret=connection.client_secret,
        technical_user_id=connection.technical_user_id,
        structure_id=connection.structure_id,
        is_sandbox=connection.is_sandbox,
    )
    stats = {'invoices_sent': 0, 'invoices_received': 0}

    try:
        # Sync sent invoices
        try:
            sent = client.search_invoices_sent(date_from, date_to)
            stats['invoices_sent'] = _sync_invoices(client, user, connection, sent)
        except Exception:
            logger.exception('Failed to sync Chorus Pro sent invoices for %s', user.email)
            stats['invoices_sent_error'] = 'Failed to sync sent invoices'

        # Sync received invoices
        try:
            received = client.search_invoices_received(date_from, date_to)
            stats['invoices_received'] = _sync_invoices(client, user, connection, received)
        except Exception:
            logger.exception('Failed to sync Chorus Pro received invoices for %s', user.email)
            stats['invoices_received_error'] = 'Failed to sync received invoices'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'Chorus Pro sync for %s: %d sent, %d received',
        user.email, stats['invoices_sent'], stats['invoices_received'],
    )
    return stats


def _sync_invoices(client: ChorusProClient, user, connection: ChorusProConnection,
                   invoice_summaries: list[dict]) -> int:
    """Fetch detail for each invoice and update_or_create. Returns count."""
    count = 0

    for summary in invoice_summaries:
        id_facture = summary.get('idFacture')
        if not id_facture:
            continue

        try:
            detail = client.get_invoice_detail(id_facture)
        except Exception:
            logger.warning('Failed to get detail for invoice %s', id_facture)
            continue

        ChorusProInvoice.objects.update_or_create(
            chorus_id=id_facture,
            defaults={
                'user': user,
                'connection': connection,
                'numero_facture': detail.get('numeroFacture', ''),
                'type_facture': detail.get('typeFacture', ''),
                'statut': detail.get('statut', ''),
                'cadre_facturation': detail.get('cadreFacturation', ''),
                'date_depot': _parse_dt(detail.get('dateDepot')),
                'date_facture': _parse_date(detail.get('dateFacture')),
                'date_echeance': _parse_date(detail.get('dateEcheance')),
                'montant_ht': Decimal(str(detail.get('montantHT', 0))),
                'montant_tva': Decimal(str(detail.get('montantTVA', 0))) if detail.get('montantTVA') is not None else None,
                'montant_ttc': Decimal(str(detail.get('montantTTC', 0))),
                'devise': detail.get('devise', 'EUR'),
                'fournisseur_name': detail.get('fournisseur', {}).get('nom', '') if detail.get('fournisseur') else '',
                'fournisseur_siret': detail.get('fournisseur', {}).get('siret', '') if detail.get('fournisseur') else '',
                'destinataire_name': detail.get('destinataire', {}).get('nom', '') if detail.get('destinataire') else '',
                'destinataire_siret': detail.get('destinataire', {}).get('siret', '') if detail.get('destinataire') else '',
                'numero_bon_commande': detail.get('numeroBonCommande', ''),
                'numero_engagement': detail.get('numeroEngagement', ''),
                'historique_statuts': detail.get('historiqueStatuts', []),
                'pieces_jointes': detail.get('piecesJointes', []),
                'commentaire': detail.get('commentaire', ''),
                'raw_data': detail,
            },
        )
        count += 1

    return count
