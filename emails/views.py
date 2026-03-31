import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Email, Transaction
from .serializers import EmailSerializer, TransactionSerializer
from .services import gmail_fetcher, microsoft_fetcher

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class EmailSyncView(APIView):
    """POST /api/emails/sync/ — fetch emails from all linked providers."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        since_date = request.data.get('since_date')
        google_count = gmail_fetcher.fetch_emails(user, since_date=since_date)
        microsoft_count = microsoft_fetcher.fetch_emails(user, since_date=since_date)
        return Response({
            'google': google_count,
            'microsoft': microsoft_count,
            'total_new': google_count + microsoft_count,
        })


@method_decorator(csrf_exempt, name='dispatch')
class EmailClassifyView(APIView):
    """POST /api/emails/classify/ — run Claude agent on unprocessed emails."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ai_agent.services.pipeline import run_pipeline
        result = run_pipeline(request.user)
        return Response(result)


class EmailListView(ListAPIView):
    """GET /api/emails/ — list fetched emails with filters."""
    serializer_class = EmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Email.objects.filter(user=self.request.user)
        provider = self.request.query_params.get('provider')
        email_status = self.request.query_params.get('status')
        if provider:
            qs = qs.filter(provider=provider)
        if email_status:
            qs = qs.filter(status=email_status)
        return qs


@method_decorator(csrf_exempt, name='dispatch')
class TransactionMergeView(APIView):
    """POST /api/emails/merge/ — run post-processing merge on transactions."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.merge import merge_related_transactions
        result = merge_related_transactions(request.user)
        return Response(result)


class TransactionListView(ListAPIView):
    """GET /api/emails/transactions/ — list extracted transactions."""
    serializer_class = TransactionSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Transaction.objects.filter(user=self.request.user)
        tx_type = self.request.query_params.get('type')
        tx_status = self.request.query_params.get('status')
        vendor = self.request.query_params.get('vendor')
        if tx_type:
            qs = qs.filter(type=tx_type)
        if tx_status:
            qs = qs.filter(status=tx_status)
        if vendor:
            qs = qs.filter(vendor_name__icontains=vendor)
        return qs
