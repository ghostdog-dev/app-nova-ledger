import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import WooCommerceConnection, WooCommerceOrder
from .serializers import WooCommerceOrderSerializer
from .services.woocommerce_sync import WooCommerceClient, sync_woocommerce_data

logger = logging.getLogger(__name__)


class WooCommerceConnectView(APIView):
    """Connect WooCommerce via REST API credentials (consumer key + secret)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        shop_url = request.data.get('shop_url', '').strip().rstrip('/')
        consumer_key = request.data.get('consumer_key', '').strip()
        consumer_secret = request.data.get('consumer_secret', '').strip()

        if not shop_url or not consumer_key or not consumer_secret:
            return Response(
                {'error': 'shop_url, consumer_key, and consumer_secret are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not consumer_key.startswith('ck_'):
            return Response(
                {'error': 'Invalid consumer_key format. Must start with ck_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not consumer_secret.startswith('cs_'):
            return Response(
                {'error': 'Invalid consumer_secret format. Must start with cs_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials with system_status endpoint
        shop_name = ''
        try:
            client = WooCommerceClient(shop_url, consumer_key, consumer_secret)
            system_status = client.get_system_status()
            environment = system_status.get('environment', {})
            shop_name = environment.get('site_title', '') or shop_url
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('WooCommerce API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'WooCommerce API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying WooCommerce credentials')
            return Response({'error': 'Failed to verify credentials'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        WooCommerceConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'shop_url': shop_url,
                'consumer_key': consumer_key,
                'consumer_secret': consumer_secret,
                'shop_name': shop_name,
                'is_active': True,
            },
        )
        logger.info('WooCommerce connected for user %s (shop: %s)', request.user.email, shop_name)

        return Response({
            'status': 'connected',
            'shop_url': shop_url,
            'shop_name': shop_name,
        })


class WooCommerceSyncView(APIView):
    """Trigger a manual WooCommerce data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_woocommerce_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('WooCommerce API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'WooCommerce API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during WooCommerce sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class WooCommerceOrdersView(APIView):
    """List user's WooCommerce orders with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = WooCommerceOrder.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        order_status = request.query_params.get('status')
        if order_status:
            qs = qs.filter(status=order_status)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date_created__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date_created__lte=date_to)

        serializer = WooCommerceOrderSerializer(qs[:500], many=True)
        return Response(serializer.data)
