"""
Computation Agent — pure Python, no LLM.

Recalculates all cluster metrics: revenue, costs, margin, tax totals.
Also computes derivable tax fields on transactions.
"""
import logging
from decimal import Decimal, InvalidOperation

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.agents.base import BaseAgent, AgentResult

logger = logging.getLogger(__name__)


class ComputationAgent(BaseAgent):
    """No LLM — pure deterministic computation."""

    def execute(self, user, context: dict) -> AgentResult:
        stats = {'clusters_updated': 0, 'tax_computed': 0}

        # 1. Compute derivable tax fields on transactions
        txs = UnifiedTransaction.objects.filter(user=user, amount__isnull=False)

        for tx in txs:
            updated = False

            if tx.amount and tx.tax_amount and not tx.amount_tax_excl:
                tx.amount_tax_excl = tx.amount - tx.tax_amount
                updated = True

            if tx.amount and tx.tax_rate and not tx.tax_amount:
                try:
                    rate = tx.tax_rate
                    tx.tax_amount = (tx.amount * rate / (Decimal('100') + rate)).quantize(Decimal('0.01'))
                    tx.amount_tax_excl = (tx.amount - tx.tax_amount).quantize(Decimal('0.01'))
                    updated = True
                except (InvalidOperation, ZeroDivisionError):
                    pass

            if tx.amount_tax_excl and tx.tax_amount and not tx.amount:
                tx.amount = tx.amount_tax_excl + tx.tax_amount
                updated = True

            if updated:
                tx.save()
                stats['tax_computed'] += 1

        # 2. Recalculate all cluster metrics
        clusters = TransactionCluster.objects.filter(user=user)
        for cluster in clusters:
            cluster.recalculate_metrics()
            stats['clusters_updated'] += 1

        logger.info(f'[Computation] Done: {stats}')
        return AgentResult(success=True, items_processed=stats['clusters_updated'], stats=stats)
