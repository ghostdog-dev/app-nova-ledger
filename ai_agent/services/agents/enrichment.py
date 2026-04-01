"""
Enrichment Agent — classifies expenses with PCG codes, vendor types, TVA.

Single-shot structured output (no agentic loop).
Worker: Haiku (structured JSON output)
Verifier: Haiku (consistency check on low-confidence results)
"""
import json
import logging
from decimal import Decimal

from django.conf import settings

from ai_agent.models import UnifiedTransaction
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = (
    "Tu es un expert-comptable français. Pour chaque transaction, détermine:\n"
    "1. pcg_code: code PCG (606=achats, 611=sous-traitance, 613=locations, 615=services numériques, "
    "616=assurances, 623=publicité, 625=déplacements/repas, 626=télécom, 627=services bancaires, "
    "628=abonnements, 641=salaires, 706=ventes services, 707=ventes marchandises)\n"
    "2. pcg_label: libellé du code\n"
    "3. category: revenue|expense_service|expense_goods|expense_shipping|purchase_cost|tax|fee|refund|transfer|salary|other\n"
    "4. business_personal: business|personal|unknown\n"
    "5. tva_deductible: true/false\n"
    "6. tax_rate: taux TVA applicable (null si inconnu)\n"
    "7. tax_amount: montant TVA calculé (null si impossible)\n"
    "8. amount_tax_excl: montant HT (null si impossible)\n"
    "9. confidence: 0.0-1.0\n\n"
    "TAUX TVA:\n"
    "- France: 20% (normal), 10% (restauration/transport), 5.5% (alimentaire/énergie), 2.1% (presse)\n"
    "- Allemagne: 19%/7% | Espagne: 21%/10% | Italie: 22%/10% | Belgique: 21%/6%\n"
    "- UK: 20%/5%/0% | Suisse: 8.1%/2.6%\n"
    "- USA/non-EU (GitHub, Stripe, AWS, Google Cloud): 0%, TVA non déductible\n\n"
    "RÈGLES TVA:\n"
    "- Montant TTC (achat consommateur): tax_amount = montant × taux / (100 + taux)\n"
    "- Montant HT (facture B2B): tax_amount = montant × taux / 100\n"
    "- En cas de doute sur TTC/HT: assumer TTC pour achats, HT pour factures B2B\n"
    "- JAMAIS inventer de montant. Si pas assez d'info, laisser null.\n\n"
    "Retourne un JSON: {\"classifications\": [{\"transaction_id\": ..., \"pcg_code\": ..., ...}]}"
)

ENRICHMENT_VERIFIER_PROMPT = (
    "Review these expense classifications for consistency. ONLY flag CLEAR errors:\n"
    "- PCG code doesn't match the vendor type (e.g. hosting classified as 625 instead of 615)\n"
    "- TVA marked deductible for a US vendor\n"
    "- Business expense classified as personal when vendor is clearly professional\n\n"
    "Be CONSERVATIVE. Only correct if 100% certain.\n\n"
    "Classifications:\n{classifications}\n\n"
    "Return corrections: [{{\"transaction_id\": <id>, \"field\": \"<field>\", "
    "\"correct_value\": <value>, \"reason\": \"...\"}}] or [] if all correct.\n"
    "No other text."
)


class EnrichmentAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model='claude-haiku-4-5-20251001',
        )
        self.verifier_model = 'claude-haiku-4-5-20251001'

    def execute(self, user, context: dict) -> AgentResult:
        from django.db.models import Q

        # Only process transactions that need work
        unclassified = UnifiedTransaction.objects.filter(
            user=user,
        ).filter(
            Q(pcg_code='') | Q(tax_amount__isnull=True)
        ).exclude(category='transfer')

        if not unclassified.exists():
            return AgentResult(success=True, items_processed=0)

        batch_size = 50
        total_classified = 0

        for i in range(0, unclassified.count(), batch_size):
            batch = list(unclassified[i:i + batch_size])
            batch_data = [
                {
                    'id': tx.id,
                    'vendor_name': tx.vendor_name,
                    'amount': str(tx.amount),
                    'currency': tx.currency,
                    'description': tx.description[:200],
                    'source_type': tx.source_type,
                    'direction': tx.direction,
                }
                for tx in batch
            ]

            # Single-shot structured output call
            try:
                response = self._call_llm_sync(
                    system=[{
                        'type': 'text',
                        'text': ENRICHMENT_SYSTEM_PROMPT,
                        'cache_control': {'type': 'ephemeral'},
                    }],
                    messages=[{
                        'role': 'user',
                        'content': json.dumps({'transactions': batch_data}, ensure_ascii=False),
                    }],
                    max_tokens=8192,
                )

                text = self._extract_text(response)
                result = self._extract_json(text)

                if result and 'classifications' in result:
                    self._apply_classifications(user, result['classifications'])
                    total_classified += len(result['classifications'])
            except Exception as e:
                logger.error(f'[Enrichment] Batch error: {e}')

        # Verifier pass — only check low confidence
        corrections = self.run_verifier(user, total_classified, context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=total_classified,
            stats={'corrections': len(corrections)},
        )

    def _apply_classifications(self, user, classifications):
        for c in classifications:
            try:
                tx = UnifiedTransaction.objects.get(id=c['transaction_id'], user=user)
                tx.pcg_code = c.get('pcg_code', tx.pcg_code)
                tx.pcg_label = c.get('pcg_label', tx.pcg_label)
                tx.category = c.get('category', tx.category)
                tx.business_personal = c.get('business_personal', tx.business_personal)
                tx.tva_deductible = c.get('tva_deductible', tx.tva_deductible)
                if c.get('tax_rate') is not None:
                    tx.tax_rate = Decimal(str(c['tax_rate']))
                if c.get('tax_amount') is not None:
                    tx.tax_amount = Decimal(str(c['tax_amount']))
                if c.get('amount_tax_excl') is not None:
                    tx.amount_tax_excl = Decimal(str(c['amount_tax_excl']))
                tx.confidence = max(tx.confidence, c.get('confidence', 0))
                tx.save()
            except (UnifiedTransaction.DoesNotExist, Exception) as e:
                logger.error(f'[Enrichment] Error applying classification: {e}')

    def run_verifier(self, user, total_classified, context: dict) -> list:
        low_conf = UnifiedTransaction.objects.filter(
            user=user, confidence__lt=0.7,
        ).exclude(pcg_code='')[:50]

        if not low_conf.exists():
            return []

        verifier_data = [
            {
                'id': tx.id,
                'vendor_name': tx.vendor_name,
                'amount': str(tx.amount),
                'pcg_code': tx.pcg_code,
                'pcg_label': tx.pcg_label,
                'category': tx.category,
                'business_personal': tx.business_personal,
                'tva_deductible': tx.tva_deductible,
            }
            for tx in low_conf
        ]

        prompt = ENRICHMENT_VERIFIER_PROMPT.format(
            classifications=json.dumps(verifier_data, ensure_ascii=False)
        )

        try:
            response = self._call_llm_sync(
                system='You are an accounting verification assistant.',
                messages=[{'role': 'user', 'content': prompt}],
                model=self.verifier_model,
            )
            text = self._extract_text(response)
            corrections = self._extract_json(text)
            if isinstance(corrections, list):
                return corrections
        except Exception as e:
            logger.warning(f'[Enrichment-Verifier] Error: {e}')

        return []

    def _apply_corrections(self, user, corrections):
        for correction in corrections:
            tx_id = correction.get('transaction_id')
            field = correction.get('field')
            value = correction.get('correct_value')
            if tx_id and field and value is not None:
                try:
                    tx = UnifiedTransaction.objects.get(id=tx_id, user=user)
                    if hasattr(tx, field):
                        setattr(tx, field, value)
                        tx.save()
                        logger.info(f'[Enrichment-Verifier] Corrected TX #{tx_id}: {field}={value}')
                except UnifiedTransaction.DoesNotExist:
                    pass
