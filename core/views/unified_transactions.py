from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import UnifiedTransaction
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
