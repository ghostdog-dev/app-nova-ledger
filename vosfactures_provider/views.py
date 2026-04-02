import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import VosFacturesClient, VosFacturesConnection, VosFacturesInvoice, VosFacturesPayment
from .serializers import (
    VosFacturesClientSerializer,
    VosFacturesInvoiceSerializer,
    VosFacturesPaymentSerializer,
)
from .services.vosfactures_sync import VosFacturesClient as VosFacturesAPIClient, sync_vosfactures_data

logger = logging.getLogger(__name__)


class VosFacturesConnectView(APIView):
    """Connect VosFactures via API token + account prefix."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_token = request.data.get('api_token', '').strip()
        account_prefix = request.data.get('account_prefix', '').strip()

        if not api_token:
            return Response({'error': 'api_token required'}, status=status.HTTP_400_BAD_REQUEST)
        if not account_prefix:
            return Response({'error': 'account_prefix required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify credentials by listing 1 invoice
        try:
            client = VosFacturesAPIClient(api_token, account_prefix)
            resp = client.client.get('/invoices.json', params={
                'api_token': api_token,
                'page': 1,
                'per_page': 1,
            })
            resp.raise_for_status()
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid API token'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('VosFactures API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'VosFactures API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except httpx.ConnectError:
            return Response(
                {'error': f'Cannot reach {account_prefix}.vosfactures.fr — check account_prefix'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Unexpected error verifying VosFactures API token')
            return Response({'error': 'Failed to verify API token'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        VosFacturesConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'api_token': api_token,
                'account_prefix': account_prefix,
                'is_active': True,
            },
        )
        logger.info('VosFactures connected for user %s (prefix: %s)', request.user.email, account_prefix)

        return Response({
            'status': 'connected',
            'account_prefix': account_prefix,
        })


class VosFacturesSyncView(APIView):
    """Trigger a manual VosFactures data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_vosfactures_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('VosFactures API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'VosFactures API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during VosFactures sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class VosFacturesInvoicesView(APIView):
    """List user's VosFactures invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = VosFacturesInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        # Filter by kind
        kind = request.query_params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)

        # Filter by income (1=sales, 0=expenses)
        income = request.query_params.get('income')
        if income is not None:
            qs = qs.filter(income=income == '1')

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(issue_date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(issue_date__lte=date_to)

        serializer = VosFacturesInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class VosFacturesPaymentsView(APIView):
    """List user's VosFactures payments."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = VosFacturesPayment.objects.filter(user=request.user).select_related('connection')

        provider = request.query_params.get('provider')
        if provider:
            qs = qs.filter(provider=provider)

        serializer = VosFacturesPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class VosFacturesClientsView(APIView):
    """List user's VosFactures clients."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = VosFacturesClient.objects.filter(user=request.user).select_related('connection')

        serializer = VosFacturesClientSerializer(qs[:500], many=True)
        return Response(serializer.data)
