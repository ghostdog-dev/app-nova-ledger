"""
LLM tool definitions and handlers for the agentic pipeline.

Each tool has:
- Schema (JSON Schema for the LLM)
- Handler (Python function that executes the tool)
"""
import json
import logging
from decimal import Decimal, InvalidOperation

from ai_agent.models import UnifiedTransaction, TransactionCluster
from ai_agent.services.normalization import normalize_vendor, vendors_match

logger = logging.getLogger(__name__)


# ============================================================
# Tool Schemas (sent to the LLM)
# ============================================================

THINK_TOOL = {
    "name": "think",
    "description": (
        "Use this tool to plan your approach BEFORE taking action. "
        "Write your analysis and action plan. This is mandatory before "
        "any create/enrich/cluster operation."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "thought": {
                "type": "string",
                "description": "Your analysis and planned action.",
            },
        },
        "required": ["thought"],
    },
}

SEARCH_TRANSACTIONS_TOOL = {
    "name": "search_transactions",
    "description": (
        "Search existing UnifiedTransactions by vendor, amount, date, reference, "
        "or source type. Use BEFORE deciding if a new transaction should be created "
        "or linked to an existing one. Vendor search is fuzzy."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "vendor_name": {"type": "string", "description": "Vendor name (fuzzy match)."},
            "amount": {"type": "number", "description": "Exact amount to match."},
            "date_from": {"type": "string", "description": "Start date (YYYY-MM-DD, inclusive)."},
            "date_to": {"type": "string", "description": "End date (YYYY-MM-DD, inclusive)."},
            "reference": {"type": "string", "description": "Invoice/order/payment reference."},
            "source_type": {"type": "string", "description": "Filter by source type."},
            "limit": {"type": "integer", "description": "Max results (default 20)."},
        },
    },
}

CREATE_CLUSTER_TOOL = {
    "name": "create_cluster",
    "description": (
        "Create a new TransactionCluster grouping related transactions. "
        "Provide a human-readable label, cluster type, and the IDs of "
        "transactions to include. Explain your reasoning."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "label": {"type": "string", "description": "Human-readable cluster label."},
            "cluster_type": {
                "type": "string",
                "enum": ["sale", "purchase", "subscription", "refund",
                         "transfer", "salary", "tax_payment", "other"],
            },
            "transaction_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "IDs of UnifiedTransactions to include.",
            },
            "reasoning": {"type": "string", "description": "Why these transactions are related."},
        },
        "required": ["label", "cluster_type", "transaction_ids", "reasoning"],
    },
}

ADD_TO_CLUSTER_TOOL = {
    "name": "add_to_cluster",
    "description": (
        "Add a transaction to an existing cluster. Specify the evidence role: "
        "confirmation (same data, different source), enrichment (adds missing data), "
        "or contradiction (conflicts with existing data)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "cluster_id": {"type": "integer", "description": "Cluster ID to add to."},
            "transaction_id": {"type": "integer", "description": "Transaction ID to add."},
            "evidence_role": {
                "type": "string",
                "enum": ["confirmation", "enrichment", "contradiction"],
            },
            "reasoning": {"type": "string"},
        },
        "required": ["cluster_id", "transaction_id", "evidence_role"],
    },
}

ENRICH_TRANSACTION_TOOL = {
    "name": "enrich_transaction",
    "description": (
        "Update fields on an existing UnifiedTransaction. Use when new data "
        "is available (from email body, cross-reference, etc.)."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "fields": {
                "type": "object",
                "description": "Fields to update: category, pcg_code, pcg_label, "
                               "business_personal, tva_deductible, vendor_type, "
                               "tax_rate, tax_amount, amount_tax_excl, description.",
            },
        },
        "required": ["transaction_id", "fields"],
    },
}

FLAG_CONTRADICTION_TOOL = {
    "name": "flag_contradiction",
    "description": (
        "Flag a contradiction between two data points for human review. "
        "Example: email says \u20ac50 but Stripe says \u20ac45."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "cluster_id": {"type": "integer", "description": "Related cluster (optional)."},
            "description": {"type": "string", "description": "What is contradictory and why."},
        },
        "required": ["transaction_id", "description"],
    },
}

CLASSIFY_EXPENSE_TOOL = {
    "name": "classify_expense",
    "description": (
        "Classify a transaction AND calculate TVA when possible. "
        "Set PCG code, category, business/personal, TVA fields. "
        "If you can determine the TVA rate, ALWAYS include tax_rate, tax_amount, amount_tax_excl."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "transaction_id": {"type": "integer"},
            "pcg_code": {"type": "string", "description": "PCG code (606, 613, 615, 625, 626, 627, 628, 706, 707, 791...)."},
            "pcg_label": {"type": "string", "description": "Human-readable label."},
            "category": {
                "type": "string",
                "enum": ["revenue", "expense_service", "expense_goods", "expense_shipping",
                         "purchase_cost", "tax", "fee", "refund", "transfer", "salary", "other"],
            },
            "business_personal": {"type": "string", "enum": ["business", "personal", "unknown"]},
            "tva_deductible": {"type": "boolean"},
            "tax_rate": {"type": "number", "description": "TVA rate (20.0, 10.0, 5.5, 2.1, 0). Null if unknown."},
            "tax_amount": {"type": "number", "description": "TVA amount calculated. Null if unknown."},
            "amount_tax_excl": {"type": "number", "description": "Amount excluding TVA. Null if unknown."},
            "confidence": {"type": "number", "description": "0.0-1.0"},
            "reasoning": {"type": "string"},
        },
        "required": ["transaction_id", "pcg_code", "pcg_label", "category",
                      "business_personal", "tva_deductible", "confidence"],
    },
}


# ============================================================
# Tool Handlers (executed by the agent framework)
# ============================================================

def make_tool_handlers(user):
    """Create tool handlers bound to a specific user."""

    def handle_think(params):
        logger.info(f'[Think] {params.get("thought", "")[:300]}')
        return {"ok": True}

    def handle_search_transactions(params):
        qs = UnifiedTransaction.objects.filter(user=user)

        if params.get('vendor_name'):
            normalized = normalize_vendor(params['vendor_name'])
            if normalized:
                qs = qs.filter(vendor_name_normalized__icontains=normalized)

        if params.get('amount') is not None:
            try:
                amt = Decimal(str(params['amount']))
                qs = qs.filter(amount=amt)
            except (InvalidOperation, ValueError):
                pass

        if params.get('date_from'):
            qs = qs.filter(transaction_date__gte=params['date_from'])
        if params.get('date_to'):
            qs = qs.filter(transaction_date__lte=params['date_to'])

        if params.get('reference'):
            qs = qs.filter(reference__icontains=params['reference'])
        if params.get('source_type'):
            qs = qs.filter(source_type=params['source_type'])

        limit = min(params.get('limit', 20), 50)
        results = qs[:limit]

        return [
            {
                'id': t.id,
                'source_type': t.source_type,
                'source_id': t.source_id,
                'direction': t.direction,
                'category': t.category,
                'amount': str(t.amount) if t.amount else None,
                'currency': t.currency,
                'transaction_date': str(t.transaction_date) if t.transaction_date else None,
                'vendor_name': t.vendor_name,
                'vendor_name_normalized': t.vendor_name_normalized,
                'description': t.description[:100],
                'reference': t.reference,
                'confidence': t.confidence,
                'cluster_id': t.cluster_id,
                'evidence_role': t.evidence_role,
            }
            for t in results
        ]

    def handle_create_cluster(params):
        tx_ids = params.get('transaction_ids', [])
        txs = UnifiedTransaction.objects.filter(user=user, id__in=tx_ids)

        if txs.count() == 0:
            return {"error": "No valid transaction IDs provided"}

        cluster = TransactionCluster.objects.create(
            user=user,
            label=params['label'],
            cluster_type=params['cluster_type'],
            match_reasoning=params.get('reasoning', ''),
            created_by='ai_agent',
        )

        txs.update(cluster=cluster)
        cluster.recalculate_metrics()

        return {
            "cluster_id": cluster.id,
            "label": cluster.label,
            "transactions_count": txs.count(),
            "margin": str(cluster.margin),
        }

    def handle_add_to_cluster(params):
        try:
            cluster = TransactionCluster.objects.get(id=params['cluster_id'], user=user)
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except (TransactionCluster.DoesNotExist, UnifiedTransaction.DoesNotExist) as e:
            return {"error": str(e)}

        tx.cluster = cluster
        tx.evidence_role = params.get('evidence_role', 'confirmation')
        tx.save()

        cluster.recalculate_metrics()

        return {
            "cluster_id": cluster.id,
            "transaction_id": tx.id,
            "evidence_role": tx.evidence_role,
            "cluster_transactions_count": cluster.transactions.count(),
        }

    def handle_enrich_transaction(params):
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except UnifiedTransaction.DoesNotExist:
            return {"error": f"Transaction {params['transaction_id']} not found"}

        fields = params.get('fields', {})
        allowed_fields = {
            'category', 'pcg_code', 'pcg_label', 'business_personal',
            'tva_deductible', 'description', 'tax_rate', 'tax_amount',
            'amount_tax_excl', 'payment_method', 'reference',
        }

        updated = []
        for field_name, value in fields.items():
            if field_name in allowed_fields:
                if field_name in ('tax_rate', 'tax_amount', 'amount_tax_excl'):
                    try:
                        value = Decimal(str(value))
                    except (InvalidOperation, ValueError):
                        continue
                setattr(tx, field_name, value)
                updated.append(field_name)

        if updated:
            tx.save()

        return {"transaction_id": tx.id, "updated_fields": updated}

    def handle_classify_expense(params):
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
        except UnifiedTransaction.DoesNotExist:
            return {"error": f"Transaction {params['transaction_id']} not found"}

        tx.pcg_code = params.get('pcg_code', tx.pcg_code)
        tx.pcg_label = params.get('pcg_label', tx.pcg_label)
        tx.category = params.get('category', tx.category)
        tx.business_personal = params.get('business_personal', tx.business_personal)
        tx.tva_deductible = params.get('tva_deductible', tx.tva_deductible)
        tx.confidence = max(tx.confidence, params.get('confidence', 0))

        # TVA fields — set only if provided and not None
        if params.get('tax_rate') is not None:
            try:
                tx.tax_rate = Decimal(str(params['tax_rate']))
            except (InvalidOperation, ValueError):
                pass
        if params.get('tax_amount') is not None:
            try:
                tx.tax_amount = Decimal(str(params['tax_amount']))
            except (InvalidOperation, ValueError):
                pass
        if params.get('amount_tax_excl') is not None:
            try:
                tx.amount_tax_excl = Decimal(str(params['amount_tax_excl']))
            except (InvalidOperation, ValueError):
                pass

        tx.save()

        return {
            "transaction_id": tx.id,
            "pcg_code": tx.pcg_code,
            "category": tx.category,
            "tax_rate": str(tx.tax_rate) if tx.tax_rate else None,
            "tax_amount": str(tx.tax_amount) if tx.tax_amount else None,
            "amount_tax_excl": str(tx.amount_tax_excl) if tx.amount_tax_excl else None,
        }

    def handle_flag_contradiction(params):
        logger.warning(
            f'[Contradiction] TX #{params["transaction_id"]}: {params["description"]}'
        )
        try:
            tx = UnifiedTransaction.objects.get(id=params['transaction_id'], user=user)
            tx.evidence_role = 'contradiction'
            tx.save()
        except UnifiedTransaction.DoesNotExist:
            pass

        return {
            "flagged": True,
            "transaction_id": params['transaction_id'],
            "description": params['description'],
        }

    return {
        'think': handle_think,
        'search_transactions': handle_search_transactions,
        'create_cluster': handle_create_cluster,
        'add_to_cluster': handle_add_to_cluster,
        'enrich_transaction': handle_enrich_transaction,
        'classify_expense': handle_classify_expense,
        'flag_contradiction': handle_flag_contradiction,
    }
