import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import SumUpConnection, SumUpPayout, SumUpTransaction
from .serializers import (
    SumUpPayoutSerializer,
    SumUpTransactionSerializer,
)
from .services.sumup_sync import SumUpClient, sync_sumup_data

logger = logging.getLogger(__name__)


class SumUpConnectView(APIView):
    """Connect SumUp via API key + merchant code."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '').strip()
        merchant_code = request.data.get('merchant_code', '').strip()

        if not api_key or not merchant_code:
            return Response({'error': 'api_key and merchant_code required'}, status=status.HTTP_400_BAD_REQUEST)

        if not api_key.startswith('sup_sk_'):
            return Response(
                {'error': 'Invalid API key format. Must start with sup_sk_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify key — fetch merchant profile
        merchant_name = ''
        default_currency = ''
        try:
            client = SumUpClient(api_key, merchant_code)
            profile = client.get_merchant_profile()
            merchant_name = profile.get('merchant_profile', {}).get('business_name', '') or profile.get('business_name', '')
            default_currency = profile.get('merchant_profile', {}).get('default_currency', '') or profile.get('default_currency', '')
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('SumUp API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'SumUp API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying SumUp API key')
            return Response({'error': 'Failed to verify API key'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        SumUpConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': api_key,
                'merchant_code': merchant_code,
                'merchant_name': merchant_name,
                'default_currency': default_currency,
                'is_active': True,
            },
        )
        logger.info('SumUp connected for user %s (merchant: %s)', request.user.email, merchant_name)

        return Response({
            'status': 'connected',
            'merchant_code': merchant_code,
            'merchant_name': merchant_name,
            'default_currency': default_currency,
        })


class SumUpSyncView(APIView):
    """Trigger a manual SumUp data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        days_back = int(request.data.get('days_back', 90))
        try:
            stats = sync_sumup_data(request.user, days_back=days_back)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('SumUp API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'SumUp API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during SumUp sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class SumUpTransactionsView(APIView):
    """List user's SumUp transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SumUpTransaction.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        tx_status = request.query_params.get('status')
        if tx_status:
            qs = qs.filter(status=tx_status)

        # Filter by type
        tx_type = request.query_params.get('type')
        if tx_type:
            qs = qs.filter(type=tx_type)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(timestamp__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(timestamp__lte=date_to)

        serializer = SumUpTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class SumUpPayoutsView(APIView):
    """List user's SumUp payouts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = SumUpPayout.objects.filter(user=request.user).select_related('connection')

        payout_status = request.query_params.get('status')
        if payout_status:
            qs = qs.filter(status=payout_status)

        serializer = SumUpPayoutSerializer(qs[:500], many=True)
        return Response(serializer.data)
