import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PennylaneConnection, PennylaneCustomerInvoice, PennylaneSupplierInvoice, PennylaneTransaction
from .serializers import (
    PennylaneCustomerInvoiceSerializer,
    PennylaneSupplierInvoiceSerializer,
    PennylaneTransactionSerializer,
)
from .services.pennylane_sync import PennylaneClient, sync_pennylane_data

logger = logging.getLogger(__name__)


class PennylaneConnectView(APIView):
    """Connect Pennylane via Bearer token. User provides token from Pennylane UI."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        access_token = request.data.get('access_token', '').strip()
        if not access_token:
            return Response({'error': 'access_token required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify token by making a test API call
        account_name = ''
        try:
            client = PennylaneClient(access_token)
            # Try listing customer invoices with limit=1 to verify the token works
            resp = client.client.get('/customer_invoices', params={'limit': 1})
            resp.raise_for_status()
            account_name = 'Pennylane account'
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid access token'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Pennylane API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Pennylane API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Pennylane access token')
            return Response({'error': 'Failed to verify access token'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        PennylaneConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': access_token,
                'account_name': account_name,
                'is_active': True,
            },
        )
        logger.info('Pennylane connected for user %s', request.user.email)

        return Response({
            'status': 'connected',
            'account_name': account_name,
        })


class PennylaneSyncView(APIView):
    """Trigger a manual Pennylane data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_pennylane_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Pennylane API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Pennylane API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Pennylane sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PennylaneCustomerInvoicesView(APIView):
    """List user's Pennylane customer invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PennylaneCustomerInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        serializer = PennylaneCustomerInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PennylaneSupplierInvoicesView(APIView):
    """List user's Pennylane supplier invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PennylaneSupplierInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        serializer = PennylaneSupplierInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PennylaneTransactionsView(APIView):
    """List user's Pennylane transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PennylaneTransaction.objects.filter(user=request.user).select_related('connection')

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        serializer = PennylaneTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)
