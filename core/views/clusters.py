from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import TransactionCluster
from core.serializers import TransactionClusterSerializer, TransactionClusterListSerializer


class ClusterListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        qs = TransactionCluster.objects.filter(user=request.user)

        cluster_type = request.query_params.get('type')
        if cluster_type:
            qs = qs.filter(cluster_type=cluster_type)

        verification = request.query_params.get('verification')
        if verification:
            qs = qs.filter(verification_status=verification)

        page = int(request.query_params.get('page', 1))
        page_size = min(int(request.query_params.get('page_size', 20)), 50)
        start = (page - 1) * page_size
        end = start + page_size

        total = qs.count()
        clusters = qs[start:end]

        serializer = TransactionClusterListSerializer(clusters, many=True)

        return Response({
            'results': serializer.data,
            'count': total,
            'page': page,
            'page_size': page_size,
        })


class ClusterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk, pk):
        try:
            cluster = TransactionCluster.objects.prefetch_related(
                'transactions'
            ).get(pk=pk, user=request.user)
        except TransactionCluster.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        serializer = TransactionClusterSerializer(cluster)
        return Response(serializer.data)


class ClusterVerifyView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, company_pk, pk):
        try:
            cluster = TransactionCluster.objects.get(pk=pk, user=request.user)
        except TransactionCluster.DoesNotExist:
            return Response({'error': 'Not found'}, status=status.HTTP_404_NOT_FOUND)

        cluster.verification_status = 'verified'
        cluster.save()
        return Response({'status': 'verified', 'cluster_id': cluster.id})
