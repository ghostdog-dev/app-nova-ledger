import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import EvolizConnection, EvolizInvoice, EvolizPayment, EvolizPurchase
from .serializers import (
    EvolizInvoiceSerializer,
    EvolizPaymentSerializer,
    EvolizPurchaseSerializer,
)
from .services.evoliz_sync import EvolizClient, sync_evoliz_data

logger = logging.getLogger(__name__)


class EvolizConnectView(APIView):
    """Connect Evoliz via public_key + secret_key + company_id."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        public_key = request.data.get('public_key', '').strip()
        secret_key = request.data.get('secret_key', '').strip()
        company_id = request.data.get('company_id', '').strip()

        if not public_key or not secret_key or not company_id:
            return Response(
                {'error': 'public_key, secret_key, and company_id are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials by getting a token
        try:
            client = EvolizClient(public_key, secret_key, company_id)
            client._get_token()  # will raise on bad credentials
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Evoliz API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Evoliz API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Evoliz credentials')
            return Response({'error': 'Failed to verify credentials'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        EvolizConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'public_key': public_key,
                'secret_key': secret_key,
                'company_id': company_id,
                'is_active': True,
            },
        )
        logger.info('Evoliz connected for user %s (company: %s)', request.user.email, company_id)

        return Response({
            'status': 'connected',
            'company_id': company_id,
        })


class EvolizSyncView(APIView):
    """Trigger a manual Evoliz data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_evoliz_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Evoliz API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Evoliz API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Evoliz sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EvolizInvoicesView(APIView):
    """List user's Evoliz invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = EvolizInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        # Filter by typedoc
        typedoc = request.query_params.get('typedoc')
        if typedoc:
            qs = qs.filter(typedoc=typedoc)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(documentdate__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(documentdate__lte=date_to)

        serializer = EvolizInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class EvolizPurchasesView(APIView):
    """List user's Evoliz purchases with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = EvolizPurchase.objects.filter(user=request.user).select_related('connection')

        purchase_status = request.query_params.get('status')
        if purchase_status:
            qs = qs.filter(status=purchase_status)

        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(documentdate__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(documentdate__lte=date_to)

        serializer = EvolizPurchaseSerializer(qs[:500], many=True)
        return Response(serializer.data)


class EvolizPaymentsView(APIView):
    """List user's Evoliz payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = EvolizPayment.objects.filter(user=request.user).select_related('connection')

        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(paydate__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(paydate__lte=date_to)

        serializer = EvolizPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)
