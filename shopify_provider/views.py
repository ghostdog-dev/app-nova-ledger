import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ShopifyConnection, ShopifyOrder
from .serializers import ShopifyOrderSerializer
from .services.shopify_sync import ShopifyClient, sync_shopify_data

logger = logging.getLogger(__name__)


class ShopifyConnectView(APIView):
    """Connect Shopify via store_name + access_token (shpat_...)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        store_name = request.data.get('store_name', '').strip()
        access_token = request.data.get('access_token', '').strip()

        if not store_name or not access_token:
            return Response(
                {'error': 'store_name and access_token are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if not access_token.startswith('shpat_'):
            return Response(
                {'error': 'Invalid access token format. Must start with shpat_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials with GET /shop.json
        shop_name = ''
        try:
            client = ShopifyClient(store_name, access_token)
            shop_data = client.get_shop()
            shop_name = shop_data.get('name', '')
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid access token'}, status=status.HTTP_401_UNAUTHORIZED)
            if e.response.status_code == 404:
                return Response({'error': 'Store not found'}, status=status.HTTP_404_NOT_FOUND)
            logger.error('Shopify API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Shopify API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Shopify credentials')
            return Response({'error': 'Failed to verify credentials'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        ShopifyConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'store_name': store_name,
                'access_token': access_token,
                'shop_name': shop_name,
                'is_active': True,
            },
        )
        logger.info('Shopify connected for user %s (store: %s)', request.user.email, store_name)

        return Response({
            'status': 'connected',
            'store_name': store_name,
            'shop_name': shop_name,
        })


class ShopifySyncView(APIView):
    """Trigger a manual Shopify data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_shopify_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Shopify API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Shopify API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Shopify sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ShopifyOrdersView(APIView):
    """List user's Shopify orders with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ShopifyOrder.objects.filter(user=request.user).select_related('connection')

        # Filter by financial_status
        financial_status = request.query_params.get('financial_status')
        if financial_status:
            qs = qs.filter(financial_status=financial_status)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at_shopify__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at_shopify__lte=date_to)

        serializer = ShopifyOrderSerializer(qs[:500], many=True)
        return Response(serializer.data)
