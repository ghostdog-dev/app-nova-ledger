"""
Correlation Agent — the core of the pipeline.

Groups UnifiedTransactions into TransactionClusters.
Any source can match any other source (no email-hub limitation).

Worker: Sonnet (complex multi-source reasoning)
Verifier: Sonnet (complex correlation audit)
"""
import json
import logging

from django.conf import settings
from django.db.models import Count

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult
from ai_agent.services.normalization import normalize_vendor
from ai_agent.services.tools import (
    THINK_TOOL, SEARCH_TRANSACTIONS_TOOL, CREATE_CLUSTER_TOOL,
    ADD_TO_CLUSTER_TOOL, FLAG_CONTRADICTION_TOOL,
    make_tool_handlers,
)

logger = logging.getLogger(__name__)

CORRELATION_SYSTEM_PROMPT = (
    "You are a financial data correlation expert. Your job is to group related "
    "transactions from DIFFERENT sources into clusters representing the SAME "
    "business operation.\n\n"
    "SOURCES: stripe (payment processor revenue), mollie (payment processor), "
    "paypal (payments), bank_api (bank debits/credits), bank_import (uploaded bank statements), "
    "email (invoices, receipts, shipping notifications).\n\n"
    "WORKFLOW for each vendor group:\n"
    "1. ALWAYS call 'think' first to analyze the transactions and plan your approach.\n"
    "2. Call 'search_transactions' to find related transactions across sources.\n"
    "3. Group related transactions into clusters using 'create_cluster'.\n"
    "4. Add confirmations/enrichments to existing clusters with 'add_to_cluster'.\n"
    "5. Flag contradictions with 'flag_contradiction'.\n\n"
    "CORRELATION RULES:\n"
    "- Same reference (invoice/order number) across sources \u2192 SAME cluster\n"
    "- Same vendor + same amount + date within 5 days \u2192 likely SAME cluster\n"
    "- Stripe charge + bank credit of same amount + 2-3 day lag \u2192 SAME (payout settlement)\n"
    "- Email invoice + bank debit of same amount/vendor \u2192 SAME cluster\n"
    "- Shipping email (no amount) + order email from same vendor \u2192 SAME cluster\n"
    "- Provider fee (Stripe fee, PayPal fee) \u2192 separate cluster type='fee'\n\n"
    "DO NOT CLUSTER:\n"
    "- Different amounts on different dates from same vendor = different transactions\n"
    "- Different order/invoice numbers = different transactions, PERIOD\n"
    "- Recurring subscriptions: each month is a SEPARATE cluster\n\n"
    "EVIDENCE ROLES when adding to clusters:\n"
    "- 'confirmation': same data from different source (increases confidence)\n"
    "- 'enrichment': adds missing info (items, tax details, tracking number)\n"
    "- 'contradiction': conflicts with existing data (different amount, etc.)\n\n"
    "Process ALL transactions. Be thorough but precise."
)

CORRELATION_VERIFIER_PROMPT = (
    "Review these transaction clusters. ONLY flag CLEAR errors:\n"
    "- Transactions with different order numbers merged together\n"
    "- Transactions with very different amounts in the same cluster\n"
    "- Transactions from completely unrelated vendors in the same cluster\n"
    "- Monthly subscriptions merged into one cluster (should be separate)\n\n"
    "Be CONSERVATIVE. Only reject if 100% certain the cluster is wrong.\n\n"
    "Clusters:\n{clusters}\n\n"
    "Return: [{{\"cluster_id\": <id>, \"action\": \"split\"|\"reject\", "
    "\"reason\": \"...\", \"transaction_ids_to_remove\": [<ids>]}}] or [] if all correct.\n"
    "No other text."
)


class CorrelationAgent(BaseAgent):

    def __init__(self, client=None):
        super().__init__(
            client=client,
            model=getattr(settings, 'AI_MODEL_CORRELATION', 'claude-sonnet-4-5-20250929'),
        )
        self.verifier_model = getattr(settings, 'AI_MODEL_CORRELATION', 'claude-sonnet-4-5-20250929')

    def execute(self, user, context: dict) -> AgentResult:
        # Get unclustered transactions
        unclustered = UnifiedTransaction.objects.filter(user=user, cluster__isnull=True)

        if not unclustered.exists():
            return AgentResult(success=True, items_processed=0)

        handlers = make_tool_handlers(user)
        tools = [
            THINK_TOOL, SEARCH_TRANSACTIONS_TOOL, CREATE_CLUSTER_TOOL,
            ADD_TO_CLUSTER_TOOL, FLAG_CONTRADICTION_TOOL,
        ]

        # Group by normalized vendor name for efficient processing
        vendor_groups = {}
        for tx in unclustered:
            key = tx.vendor_name_normalized or 'unknown'
            vendor_groups.setdefault(key, []).append(tx)

        clusters_created = 0
        total_processed = 0

        # Process vendor groups in batches
        batch_vendors = []
        batch_txs = []

        for vendor, txs in vendor_groups.items():
            batch_vendors.append(vendor)
            batch_txs.extend(txs)

            # Process when batch is big enough or last vendor
            if len(batch_txs) >= 30 or vendor == list(vendor_groups.keys())[-1]:
                batch_data = [
                    {
                        'id': tx.id,
                        'source_type': tx.source_type,
                        'direction': tx.direction,
                        'vendor_name': tx.vendor_name,
                        'vendor_normalized': tx.vendor_name_normalized,
                        'amount': str(tx.amount) if tx.amount else None,
                        'currency': tx.currency,
                        'transaction_date': str(tx.transaction_date) if tx.transaction_date else None,
                        'reference': tx.reference,
                        'description': tx.description[:80],
                        'category': tx.category,
                    }
                    for tx in batch_txs
                ]

                user_msg = (
                    f"Correlate these {len(batch_data)} unclustered transactions "
                    f"from vendors: {', '.join(batch_vendors)}.\n"
                    f"Also search for existing clustered transactions that these might match.\n\n"
                    f"Transactions:\n{json.dumps(batch_data, ensure_ascii=False)}"
                )

                try:
                    messages, stats = self._run_agentic_loop(
                        system=CORRELATION_SYSTEM_PROMPT,
                        messages=[{'role': 'user', 'content': user_msg}],
                        tools=tools,
                        tool_handlers=handlers,
                        max_iterations=len(batch_txs) + 10,
                    )
                    total_processed += len(batch_txs)
                except Exception as e:
                    logger.error(f'[Correlation] Batch error: {e}')

                batch_vendors = []
                batch_txs = []

        # Count clusters created
        clusters_created = TransactionCluster.objects.filter(
            user=user, created_by='ai_agent'
        ).count()

        # Run verifier
        corrections = self.run_verifier(user, [], context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=total_processed,
            stats={
                'clusters_created': clusters_created,
                'corrections': len(corrections),
            },
        )

    def run_verifier(self, user, results: list, context: dict) -> list:
        recent_clusters = TransactionCluster.objects.filter(
            user=user, verification_status='auto',
        ).prefetch_related('transactions')[:50]

        if not recent_clusters:
            return []

        clusters_data = []
        for cluster in recent_clusters:
            txs = cluster.transactions.all()
            clusters_data.append({
                'cluster_id': cluster.id,
                'label': cluster.label,
                'type': cluster.cluster_type,
                'confidence': cluster.confidence,
                'margin': str(cluster.margin),
                'transactions': [
                    {
                        'id': tx.id,
                        'source': tx.source_type,
                        'vendor': tx.vendor_name,
                        'amount': str(tx.amount),
                        'date': str(tx.transaction_date),
                        'reference': tx.reference,
                        'evidence_role': tx.evidence_role,
                    }
                    for tx in txs
                ],
            })

        prompt = CORRELATION_VERIFIER_PROMPT.format(
            clusters=json.dumps(clusters_data, ensure_ascii=False)
        )

        try:
            response = self._call_llm_sync(
                system='You are a financial data correlation auditor.',
                messages=[{'role': 'user', 'content': prompt}],
                model=self.verifier_model,
            )
            text = self._extract_text(response)
            corrections = self._extract_json(text)
            if isinstance(corrections, list):
                return corrections
        except Exception as e:
            logger.warning(f'[Correlation-Verifier] Error: {e}')

        return []

    def _apply_corrections(self, user, corrections):
        for correction in corrections:
            cluster_id = correction.get('cluster_id')
            action = correction.get('action')
            tx_ids = correction.get('transaction_ids_to_remove', [])

            if action == 'reject' and cluster_id:
                try:
                    cluster = TransactionCluster.objects.get(id=cluster_id, user=user)
                    cluster.transactions.all().update(cluster=None)
                    cluster.delete()
                    logger.info(f'[Correlation-Verifier] Rejected cluster #{cluster_id}')
                except TransactionCluster.DoesNotExist:
                    pass

            elif action == 'split' and tx_ids:
                UnifiedTransaction.objects.filter(
                    user=user, id__in=tx_ids
                ).update(cluster=None)
                if cluster_id:
                    try:
                        cluster = TransactionCluster.objects.get(id=cluster_id, user=user)
                        cluster.recalculate_metrics()
                    except TransactionCluster.DoesNotExist:
                        pass
                logger.info(
                    f'[Correlation-Verifier] Split TX {tx_ids} from cluster #{cluster_id}'
                )
