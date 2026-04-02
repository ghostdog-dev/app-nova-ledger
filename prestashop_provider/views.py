import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PrestaShopConnection, PrestaShopOrder, PrestaShopPayment
from .serializers import PrestaShopOrderSerializer, PrestaShopPaymentSerializer
from .services.prestashop_sync import PrestaShopClient, sync_prestashop_data

logger = logging.getLogger(__name__)


class PrestaShopConnectView(APIView):
    """Connect PrestaShop via shop URL + API key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        shop_url = request.data.get('shop_url', '').strip().rstrip('/')
        api_key = request.data.get('api_key', '').strip()

        if not shop_url:
            return Response({'error': 'shop_url required'}, status=status.HTTP_400_BAD_REQUEST)
        if not api_key:
            return Response({'error': 'api_key required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify connection by hitting the API root
        shop_name = ''
        try:
            client = PrestaShopClient(shop_url, api_key)
            info = client.verify()
            shop_name = info.get('shop_name', '')
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('PrestaShop API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'PrestaShop API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying PrestaShop API key')
            return Response({'error': 'Failed to verify API key'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        PrestaShopConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'shop_url': shop_url,
                'api_key': api_key,
                'shop_name': shop_name,
                'is_active': True,
            },
        )
        logger.info('PrestaShop connected for user %s (shop: %s)', request.user.email, shop_name)

        return Response({
            'status': 'connected',
            'shop_url': shop_url,
            'shop_name': shop_name,
        })


class PrestaShopSyncView(APIView):
    """Trigger a manual PrestaShop data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_prestashop_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('PrestaShop API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'PrestaShop API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during PrestaShop sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PrestaShopOrdersView(APIView):
    """List user's PrestaShop orders with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PrestaShopOrder.objects.filter(user=request.user).select_related('connection')

        # Filter by state
        state = request.query_params.get('state')
        if state:
            qs = qs.filter(current_state=state)

        # Filter by payment method
        method = request.query_params.get('payment_method')
        if method:
            qs = qs.filter(payment_method=method)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date_add__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date_add__lte=date_to)

        serializer = PrestaShopOrderSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PrestaShopPaymentsView(APIView):
    """List user's PrestaShop payments."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PrestaShopPayment.objects.filter(user=request.user).select_related('connection')

        # Filter by payment method
        method = request.query_params.get('payment_method')
        if method:
            qs = qs.filter(payment_method=method)

        serializer = PrestaShopPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)
