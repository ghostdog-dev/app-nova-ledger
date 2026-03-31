"""
Verification Agent — audits clusters with low confidence or contradictions.

Uses Haiku for simple checks, Sonnet for complex anomalies.
Fresh context — no self-confirmation (rapport S3.2).
"""
import json
import logging
from decimal import Decimal

from django.conf import settings

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

VERIFICATION_SYSTEM_PROMPT = (
    "You are a financial data auditor. Review these transaction clusters "
    "for anomalies and quality issues.\n\n"
    "CHECK FOR:\n"
    "1. Amount mismatches: bank debit \u2260 invoice amount in same cluster\n"
    "2. Date outliers: transactions > 14 days apart in same cluster\n"
    "3. Currency mismatches: different currencies without conversion explanation\n"
    "4. Missing data: cluster marked complete but missing key fields\n"
    "5. Suspicious margins: negative margin on a sale, or margin > 90%\n"
    "6. Tax inconsistencies: amount_tax_excl + tax_amount \u2260 amount\n\n"
    "For each issue found, return:\n"
    "{\"cluster_id\": <id>, \"severity\": \"critical\"|\"warning\"|\"info\", "
    "\"issue\": \"description\", \"suggestion\": \"what to fix\"}\n\n"
    "Return JSON array. Empty array if no issues."
)


class VerificationAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model=getattr(settings, 'AI_MODEL_VERIFIER', 'claude-haiku-4-5-20251001'),
        )
        self.sonnet_model = getattr(settings, 'AI_MODEL_CLASSIFICATION', 'claude-sonnet-4-5-20250929')

    def execute(self, user, context: dict) -> AgentResult:
        anomalies = []

        # 1. Quick deterministic checks (no LLM)
        anomalies.extend(self._check_tax_consistency(user))
        anomalies.extend(self._check_date_outliers(user))

        # 2. LLM audit of low-confidence clusters
        low_confidence = TransactionCluster.objects.filter(
            user=user, confidence__lt=0.8, verification_status='auto',
        ).prefetch_related('transactions')[:20]

        if low_confidence:
            llm_anomalies = self._llm_audit(low_confidence)
            anomalies.extend(llm_anomalies)

        # 3. LLM audit of contradictions (use Sonnet — complex)
        contradictions = UnifiedTransaction.objects.filter(
            user=user, evidence_role='contradiction',
        )
        if contradictions.exists():
            contradiction_anomalies = self._audit_contradictions(user, contradictions)
            anomalies.extend(contradiction_anomalies)

        logger.info(f'[Verification] Found {len(anomalies)} anomalies')
        return AgentResult(
            success=True,
            items_processed=len(anomalies),
            stats={
                'anomalies_total': len(anomalies),
                'critical': sum(1 for a in anomalies if a.get('severity') == 'critical'),
                'warnings': sum(1 for a in anomalies if a.get('severity') == 'warning'),
            },
        )

    def _check_tax_consistency(self, user) -> list:
        """Deterministic: check amount = amount_tax_excl + tax_amount."""
        anomalies = []
        txs = UnifiedTransaction.objects.filter(
            user=user,
            amount__isnull=False,
            amount_tax_excl__isnull=False,
            tax_amount__isnull=False,
        )
        for tx in txs:
            expected = tx.amount_tax_excl + tx.tax_amount
            diff = abs(tx.amount - expected)
            if diff > Decimal('0.02'):
                anomalies.append({
                    'transaction_id': tx.id,
                    'severity': 'warning',
                    'issue': f'Tax inconsistency: {tx.amount} != {tx.amount_tax_excl} + {tx.tax_amount} (diff={diff})',
                    'suggestion': 'Recompute tax fields or flag for manual review.',
                })
        return anomalies

    def _check_date_outliers(self, user) -> list:
        """Deterministic: check for clusters with transactions > 14 days apart."""
        from django.db.models import Max, Min
        anomalies = []
        clusters = TransactionCluster.objects.filter(user=user).annotate(
            min_date=Min('transactions__transaction_date'),
            max_date=Max('transactions__transaction_date'),
        )
        for cluster in clusters:
            if cluster.min_date and cluster.max_date:
                span = (cluster.max_date - cluster.min_date).days
                if span > 14:
                    anomalies.append({
                        'cluster_id': cluster.id,
                        'severity': 'warning',
                        'issue': f'Date span {span} days in cluster "{cluster.label}"',
                        'suggestion': 'Check if all transactions belong together.',
                    })
        return anomalies

    def _llm_audit(self, clusters) -> list:
        clusters_data = []
        for cluster in clusters:
            txs = cluster.transactions.all()
            clusters_data.append({
                'cluster_id': cluster.id,
                'label': cluster.label,
                'type': cluster.cluster_type,
                'margin': str(cluster.margin),
                'confidence': cluster.confidence,
                'corroboration_score': cluster.corroboration_score,
                'transactions': [
                    {
                        'id': tx.id, 'source': tx.source_type,
                        'vendor': tx.vendor_name, 'amount': str(tx.amount),
                        'currency': tx.currency,
                        'date': str(tx.transaction_date),
                    }
                    for tx in txs
                ],
            })

        try:
            response = self._call_llm_sync(
                system=VERIFICATION_SYSTEM_PROMPT,
                messages=[{
                    'role': 'user',
                    'content': json.dumps(clusters_data, ensure_ascii=False),
                }],
            )
            text = self._extract_text(response)
            result = self._extract_json(text)
            if isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f'[Verification] LLM audit error: {e}')

        return []

    def _audit_contradictions(self, user, contradictions) -> list:
        data = [
            {
                'id': tx.id, 'vendor': tx.vendor_name, 'amount': str(tx.amount),
                'source': tx.source_type, 'cluster_id': tx.cluster_id,
                'description': tx.description[:100],
            }
            for tx in contradictions[:20]
        ]

        try:
            response = self._call_llm_sync(
                system=(
                    "Review these flagged contradictions. For each, determine:\n"
                    "1. Which data source is more trustworthy?\n"
                    "2. What action should be taken?\n"
                    "Return: [{\"id\": <tx_id>, \"severity\": \"critical\"|\"warning\", "
                    "\"issue\": \"...\", \"suggestion\": \"...\"}]"
                ),
                messages=[{'role': 'user', 'content': json.dumps(data, ensure_ascii=False)}],
                model=self.sonnet_model,
            )
            text = self._extract_text(response)
            result = self._extract_json(text)
            if isinstance(result, list):
                return result
        except Exception as e:
            logger.warning(f'[Verification] Contradiction audit error: {e}')

        return []
