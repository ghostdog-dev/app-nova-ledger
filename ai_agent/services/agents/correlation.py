"""
Correlation Agent — groups UnifiedTransactions into TransactionClusters.

Uses pre-fetched context + single-shot structured output instead of agentic loop.
Worker: Haiku (pattern matching on pre-fetched data)
Verifier: Haiku (independent audit of recent clusters)
"""
import json
import logging

from django.conf import settings

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)

CORRELATION_SYSTEM_PROMPT = (
    "Tu es un expert en rapprochement de données financières. "
    "On te donne des transactions non-clusterisées et des clusters existants.\n\n"
    "RÈGLES:\n"
    "- Même référence (facture/commande) = même cluster\n"
    "- Même vendor + même montant + date à 5 jours près = même cluster\n"
    "- Stripe charge + bank credit même montant + 2-3j = même cluster (payout)\n"
    "- Email facture + débit bancaire même montant/vendor = même cluster\n"
    "- Commandes différentes (numéros différents) = clusters séparés\n"
    "- Abonnements récurrents: chaque mois = cluster séparé\n\n"
    "ACTIONS:\n"
    "- new_clusters: grouper des transactions non-clusterisées ensemble\n"
    "- add_to_existing: ajouter une transaction à un cluster existant\n"
    "- contradictions: signaler des incohérences\n\n"
    "Retourne JSON: {\"new_clusters\": [{\"label\": ..., \"cluster_type\": \"sale|purchase|subscription|refund|transfer|other\", "
    "\"transaction_ids\": [...], \"reasoning\": ...}], "
    "\"add_to_existing\": [{\"cluster_id\": ..., \"transaction_id\": ..., \"evidence_role\": \"confirmation|enrichment|contradiction\"}], "
    "\"contradictions\": [{\"transaction_id\": ..., \"description\": ...}]}"
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
            model='claude-haiku-4-5-20251001',
        )
        self.verifier_model = 'claude-haiku-4-5-20251001'

    def execute(self, user, context: dict) -> AgentResult:
        unclustered = UnifiedTransaction.objects.filter(user=user, cluster__isnull=True)
        if not unclustered.exists():
            return AgentResult(success=True, items_processed=0)

        # Group by normalized vendor
        vendor_groups = {}
        for tx in unclustered:
            key = tx.vendor_name_normalized or 'unknown'
            vendor_groups.setdefault(key, []).append(tx)

        # Process in batches of ~50 transactions
        batch = []
        batch_vendors = []
        clusters_created = 0
        vendor_keys = list(vendor_groups.keys())

        for vendor in vendor_keys:
            txs = vendor_groups[vendor]
            batch.extend(txs)
            batch_vendors.append(vendor)

            if len(batch) >= 50 or vendor == vendor_keys[-1]:
                # Pre-fetch existing clustered transactions for these vendors
                existing = UnifiedTransaction.objects.filter(
                    user=user,
                    cluster__isnull=False,
                    vendor_name_normalized__in=batch_vendors,
                ).select_related('cluster')[:100]

                existing_data = [
                    {
                        'id': tx.id,
                        'vendor': tx.vendor_name,
                        'amount': str(tx.amount),
                        'date': str(tx.transaction_date),
                        'source': tx.source_type,
                        'cluster_id': tx.cluster_id,
                        'cluster_label': tx.cluster.label if tx.cluster else None,
                    }
                    for tx in existing
                ]

                batch_data = [
                    {
                        'id': tx.id,
                        'source_type': tx.source_type,
                        'direction': tx.direction,
                        'vendor_name': tx.vendor_name,
                        'amount': str(tx.amount) if tx.amount else None,
                        'currency': tx.currency,
                        'transaction_date': str(tx.transaction_date) if tx.transaction_date else None,
                        'reference': tx.reference,
                        'description': tx.description[:100] if tx.description else '',
                        'category': tx.category,
                    }
                    for tx in batch
                ]

                # Single LLM call with structured output
                user_msg = json.dumps(
                    {'unclustered': batch_data, 'existing_clusters': existing_data},
                    ensure_ascii=False,
                )

                try:
                    response = self._call_llm_sync(
                        system=[{
                            'type': 'text',
                            'text': CORRELATION_SYSTEM_PROMPT,
                            'cache_control': {'type': 'ephemeral'},
                        }],
                        messages=[{'role': 'user', 'content': user_msg}],
                        max_tokens=8192,
                    )

                    text = self._extract_text(response)
                    result = self._extract_json(text)

                    if result:
                        clusters_created += self._apply_results(user, result)
                except Exception as e:
                    logger.error(f'[Correlation] Batch error: {e}')

                batch = []
                batch_vendors = []

        # Verifier
        corrections = self.run_verifier(user, [], context)
        if corrections:
            self._apply_corrections(user, corrections)

        return AgentResult(
            success=True,
            items_processed=unclustered.count(),
            stats={
                'clusters_created': clusters_created,
                'corrections': len(corrections),
            },
        )

    def _apply_results(self, user, result):
        clusters_created = 0

        # Create new clusters
        for cluster_data in result.get('new_clusters', []):
            tx_ids = cluster_data.get('transaction_ids', [])
            txs = UnifiedTransaction.objects.filter(user=user, id__in=tx_ids)
            if not txs.exists():
                continue
            cluster = TransactionCluster.objects.create(
                user=user,
                label=cluster_data.get('label', ''),
                cluster_type=cluster_data.get('cluster_type', 'other'),
                match_reasoning=cluster_data.get('reasoning', ''),
                created_by='ai_agent',
            )
            txs.update(cluster=cluster)
            cluster.recalculate_metrics()
            clusters_created += 1

        # Add to existing clusters
        for addition in result.get('add_to_existing', []):
            try:
                cluster = TransactionCluster.objects.get(
                    id=addition['cluster_id'], user=user,
                )
                tx = UnifiedTransaction.objects.get(
                    id=addition['transaction_id'], user=user,
                )
                tx.cluster = cluster
                tx.evidence_role = addition.get('evidence_role', 'confirmation')
                tx.save()
                cluster.recalculate_metrics()
            except (TransactionCluster.DoesNotExist, UnifiedTransaction.DoesNotExist):
                pass

        # Flag contradictions
        for flag in result.get('contradictions', []):
            try:
                tx = UnifiedTransaction.objects.get(
                    id=flag['transaction_id'], user=user,
                )
                tx.evidence_role = 'contradiction'
                tx.save()
            except UnifiedTransaction.DoesNotExist:
                pass

        return clusters_created

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
            clusters=json.dumps(clusters_data, ensure_ascii=False),
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
                    user=user, id__in=tx_ids,
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
