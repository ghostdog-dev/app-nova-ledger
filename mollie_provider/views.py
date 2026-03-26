import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import httpx

from .models import (
    MollieConnection,
    MollieInvoice,
    MolliePayment,
    MollieRefund,
    MollieSettlement,
)
from .serializers import (
    MolliePaymentSerializer,
    MollieRefundSerializer,
    MollieSettlementSerializer,
)
from .services.mollie_sync import MollieClient, sync_mollie_data

logger = logging.getLogger(__name__)


class MollieConnectView(APIView):
    """Connect a Mollie account by providing an API key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '').strip()
        if not api_key:
            return Response(
                {'error': 'api_key is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the API key by calling /v2/organizations/me
        client = MollieClient(api_key)
        try:
            org = client.get_organization()
        except httpx.HTTPStatusError as e:
            logger.error('Mollie API key verification failed: %s', e.response.status_code)
            return Response(
                {'error': f'Invalid API key or Mollie API error: {e.response.status_code}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Unexpected error verifying Mollie API key')
            return Response(
                {'error': 'Failed to verify API key'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        finally:
            client.close()

        # Create or update the connection
        connection, created = MollieConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': api_key,
                'organization_id': org.get('id', ''),
                'organization_name': org.get('name', ''),
                'is_active': True,
            },
        )

        action = 'connected' if created else 'updated'
        logger.info('Mollie %s for user %s (org: %s)', action, request.user.email, connection.organization_name)

        return Response({
            'status': action,
            'organization_id': connection.organization_id,
            'organization_name': connection.organization_name,
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
