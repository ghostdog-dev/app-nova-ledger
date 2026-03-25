import logging

from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Email, Transaction
from .serializers import EmailSerializer, TransactionSerializer
from .services import gmail_fetcher, microsoft_fetcher

logger = logging.getLogger(__name__)


class EmailSyncView(APIView):
    """POST /api/emails/sync/ — fetch emails from all linked providers."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        google_count = gmail_fetcher.fetch_emails(user)
        microsoft_count = microsoft_fetcher.fetch_emails(user)
        return Response({
            'google': google_count,
            'microsoft': microsoft_count,
            'total_new': google_count + microsoft_count,
        })


class EmailClassifyView(APIView):
    """POST /api/emails/classify/ — run Claude agent on unprocessed emails."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.agent import classify_emails
        result = classify_emails(request.user)
        return Response(result)


class EmailListView(ListAPIView):
    """GET /api/emails/ — list fetched emails with filters."""
    serializer_class = EmailSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = Email.objects.filter(user=self.request.user)
        # Filters
        provider = self.request.query_params.get('provider')
        email_status = self.request.query_params.get('status')
        if provider:
            qs = qs.filter(provider=provider)
        if email_status:
            qs = qs.filter(status=email_status)
        return qs


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
