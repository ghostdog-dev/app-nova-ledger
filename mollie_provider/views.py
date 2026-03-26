import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import MollieConnection, MollieInvoice, MolliePayment, MollieRefund, MollieSettlement
from .serializers import (
    MollieInvoiceSerializer,
    MolliePaymentSerializer,
    MollieRefundSerializer,
    MollieSettlementSerializer,
)
from .services.mollie_sync import MollieClient, sync_mollie_data

logger = logging.getLogger(__name__)


class MollieConnectView(APIView):
    """Connect Mollie via API key. User provides test_... or live_... key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '').strip()
        if not api_key:
            return Response({'error': 'api_key required'}, status=status.HTTP_400_BAD_REQUEST)

        if not api_key.startswith(('test_', 'live_')):
            return Response(
                {'error': 'Invalid API key format. Must start with test_ or live_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify key — use /v2/methods (works in test mode) or /v2/organizations/me (live only)
        org_id = ''
        org_name = ''
        try:
            client = MollieClient(api_key)
            if api_key.startswith('live_'):
                org_data = client.get_organization()
                org_id = org_data.get('id', '')
                org_name = org_data.get('name', '')
            else:
                # Test mode: /v2/organizations/me doesn't work, use /v2/methods to verify key
                resp = client.client.get('/methods')
                resp.raise_for_status()
                methods = resp.json()
                org_name = f'Test account ({methods.get("count", 0)} payment methods)'
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Mollie API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Mollie API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Mollie API key')
            return Response({'error': 'Failed to verify API key'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        MollieConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': api_key,
                'organization_id': org_id,
                'organization_name': org_name,
                'is_active': True,
            },
        )
        logger.info('Mollie connected for user %s (org: %s)', request.user.email, org_name)

        return Response({
            'status': 'connected',
            'organization_id': org_id,
            'organization_name': org_name,
            'key_type': 'test' if api_key.startswith('test_') else 'live',
        })


class MollieSyncView(APIView):
    """Trigger a manual Mollie data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_mollie_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Mollie API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Mollie API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Mollie sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MolliePaymentsView(APIView):
    """List user's Mollie payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MolliePayment.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        payment_status = request.query_params.get('status')
        if payment_status:
            qs = qs.filter(status=payment_status)

        # Filter by method
        method = request.query_params.get('method')
        if method:
            qs = qs.filter(method=method)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at_mollie__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at_mollie__lte=date_to)

        serializer = MolliePaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieRefundsView(APIView):
    """List user's Mollie refunds."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieRefund.objects.filter(user=request.user).select_related('connection')

        refund_status = request.query_params.get('status')
        if refund_status:
            qs = qs.filter(status=refund_status)

        serializer = MollieRefundSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieSettlementsView(APIView):
    """List user's Mollie settlements."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieSettlement.objects.filter(user=request.user).select_related('connection')

        settlement_status = request.query_params.get('status')
        if settlement_status:
            qs = qs.filter(status=settlement_status)

        serializer = MollieSettlementSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieInvoicesView(APIView):
    """List user's Mollie invoices."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        serializer = MollieInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)
