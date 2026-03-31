"""
Enrichment Agent — classifies expenses with PCG codes, vendor types, TVA.

Worker: Sonnet (complex accounting reasoning)
Verifier: Haiku (simple consistency check)
"""
import json
import logging

from django.conf import settings

from ai_agent.models import UnifiedTransaction
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.tools import (
    THINK_TOOL, CLASSIFY_EXPENSE_TOOL, ENRICH_TRANSACTION_TOOL,
    make_tool_handlers,
)

logger = logging.getLogger(__name__)

ENRICHMENT_SYSTEM_PROMPT = (
    "You are a French accounting expert (expert-comptable) classifying financial transactions.\n\n"
    "For each transaction, you MUST:\n"
    "1. Call 'think' to analyze the transaction and plan your classification.\n"
    "2. Call 'classify_expense' with your classification.\n\n"
    "Classification rules:\n"
    "- PCG codes: 606=achats marchandises, 611=sous-traitance, 613=locations, "
    "615=services num\u00e9riques/h\u00e9bergement, 616=assurances, 623=publicit\u00e9, "
    "625=d\u00e9placements/missions/r\u00e9ceptions, 626=frais postaux/t\u00e9l\u00e9com, "
    "627=services bancaires/commissions, 628=divers (abonnements), "
    "641=r\u00e9mun\u00e9rations personnel, 791=transferts de charges.\n"
    "- business_personal: 'business' if clearly professional, 'personal' if clearly personal, "
    "'unknown' if ambiguous (e.g. Uber Eats could be either).\n"
    "- tva_deductible: true for business expenses from FR/EU vendors. "
    "false for personal, non-EU vendors (US SaaS = no TVA), or when unsure.\n"
    "- Category: match to the best category based on the vendor and description.\n\n"
    "Process ALL transactions in the batch. Be efficient."
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
            model=getattr(settings, 'AI_MODEL_CLASSIFICATION', 'claude-sonnet-4-5-20250929'),
        )
        self.verifier_model = getattr(settings, 'AI_MODEL_VERIFIER', 'claude-haiku-4-5-20251001')

    def execute(self, user, context: dict) -> AgentResult:
        # Get unclassified transactions (no pcg_code yet)
        unclassified = UnifiedTransaction.objects.filter(
            user=user, pcg_code='', direction='outflow',
        ).exclude(category='transfer')

        if not unclassified.exists():
            return AgentResult(success=True, items_processed=0)

        batch_size = 20
        total_classified = 0
        all_classifications = []
        handlers = make_tool_handlers(user)

        # Process in batches
        for i in range(0, unclassified.count(), batch_size):
            batch = list(unclassified[i:i + batch_size])
            batch_data = [
                {
                    'id': tx.id,
                    'vendor_name': tx.vendor_name,
                    'amount': str(tx.amount) if tx.amount else '?',
                    'currency': tx.currency,
                    'description': tx.description[:100],
                    'source_type': tx.source_type,
                    'category': tx.category,
                }
                for tx in batch
            ]

            user_msg = (
                f"Classify these {len(batch)} transactions. "
                f"For each: 1) think, 2) classify_expense.\n\n"
                f"Transactions:\n{json.dumps(batch_data, ensure_ascii=False)}"
            )

            tools = [THINK_TOOL, CLASSIFY_EXPENSE_TOOL]

            try:
                messages, stats = self._run_agentic_loop(
                    system=ENRICHMENT_SYSTEM_PROMPT,
                    messages=[{'role': 'user', 'content': user_msg}],
                    tools=tools,
                    tool_handlers=handlers,
                    max_iterations=len(batch) + 5,
                )
                total_classified += len(batch)
                all_classifications.extend(batch_data)
            except Exception as e:
                logger.error(f'[Enrichment] Batch error: {e}')

        # Run verifier on all classifications
        corrections = self.run_verifier(user, all_classifications, context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=total_classified,
            stats={'classifications': total_classified, 'corrections': len(corrections)},
        )

    def run_verifier(self, user, classifications: list, context: dict) -> list:
        if not classifications:
            return []

        # Re-read the classified transactions for verification
        tx_ids = [c['id'] for c in classifications]
        txs = UnifiedTransaction.objects.filter(user=user, id__in=tx_ids)
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
            for tx in txs
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
