from django.db.models import Count

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import UnifiedTransaction, TransactionCluster
from core.serializers import UnifiedTransactionSerializer


class UnifiedTransactionListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        qs = UnifiedTransaction.objects.filter(user=request.user)

        # Filters
        source = request.query_params.get('source')
        if source:
            qs = qs.filter(source_type=source)

        direction = request.query_params.get('direction')
        if direction:
            qs = qs.filter(direction=direction)

        category = request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)

        reconciliation_status = request.query_params.get('status')
        if reconciliation_status == 'matched':
            qs = qs.filter(cluster__isnull=False, cluster__is_complete=True)
        elif reconciliation_status == 'pending':
            qs = qs.filter(cluster__isnull=False, cluster__is_complete=False)
        elif reconciliation_status == 'orphan':
            qs = qs.filter(cluster__isnull=True)

        # Pagination
        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 50)), 100)
        start = (page - 1) * page_size
        end = start + page_size

        total = qs.count()
        transactions = qs[start:end]

        serializer = UnifiedTransactionSerializer(transactions, many=True)

        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
            'total_pages': (total + page_size - 1) // page_size,
        })


class UnifiedStatsView(APIView):
    """GET /companies/{id}/unified-stats/ — KPIs for the unified ledger."""
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        qs = UnifiedTransaction.objects.filter(user=request.user).select_related('cluster')
        total = qs.count()
        if total == 0:
            return Response({
                'totalTransactions': 0, 'clustered': 0, 'orphan': 0,
                'enriched': 0, 'clusters': 0, 'completeClusters': 0,
                'averageScore': 0, 'bySource': {},
            })

        clustered = qs.filter(cluster__isnull=False).count()
        orphan = total - clustered
        enriched = qs.exclude(pcg_code='').count()
        clusters = TransactionCluster.objects.filter(user=request.user).count()
        complete_clusters = TransactionCluster.objects.filter(
            user=request.user, is_complete=True
        ).count()

        # Average accounting score
        score_total = 0
        for tx in qs.iterator():
            s = 0
            if tx.amount and tx.amount != 0:
                s += 20
            if tx.transaction_date:
                s += 10
            if tx.vendor_name and tx.vendor_name.strip():
                s += 15
            if tx.pcg_code:
                s += 15
            if tx.cluster_id:
                s += 15
            if tx.tax_amount or tx.tax_rate:
                s += 10
            if tx.cluster_id:
                bank_sources = {'bank_api', 'bank_import'}
                sources = set(
                    tx.cluster.transactions.values_list('source_type', flat=True)
                )
                if sources & bank_sources:
                    s += 15
            score_total += s
        avg_score = round(score_total / total)

        # By source
        by_source = dict(
            qs.values_list('source_type')
            .annotate(c=Count('id'))
            .values_list('source_type', 'c')
        )

        return Response({
            'totalTransactions': total,
            'clustered': clustered,
            'orphan': orphan,
            'enriched': enriched,
            'clusters': clusters,
            'completeClusters': complete_clusters,
            'averageScore': avg_score,
            'bySource': by_source,
        })
