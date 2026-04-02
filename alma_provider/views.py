import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AlmaConnection, AlmaPayment
from .serializers import AlmaPaymentSerializer
from .services.alma_sync import AlmaClient, sync_alma_data

logger = logging.getLogger(__name__)


class AlmaConnectView(APIView):
    """Connect Alma via API key. User provides sk_test_... or sk_live_... key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '').strip()
        if not api_key:
            return Response({'error': 'api_key required'}, status=status.HTTP_400_BAD_REQUEST)

        if not api_key.startswith(('sk_test_', 'sk_live_')):
            return Response(
                {'error': 'Invalid API key format. Must start with sk_test_ or sk_live_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_sandbox = api_key.startswith('sk_test_')

        # Verify key by listing 1 payment
        try:
            client = AlmaClient(api_key)
            resp = client.client.get('/payments', params={'limit': 1})
            resp.raise_for_status()
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid API key'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Alma API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Alma API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Alma API key')
            return Response({'error': 'Failed to verify API key'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        AlmaConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'api_key': api_key,
                'is_sandbox': is_sandbox,
                'is_active': True,
            },
        )
        logger.info('Alma connected for user %s (sandbox=%s)', request.user.email, is_sandbox)

        return Response({
            'status': 'connected',
            'is_sandbox': is_sandbox,
            'key_type': 'test' if is_sandbox else 'live',
        })


class AlmaSyncView(APIView):
    """Trigger a manual Alma data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_alma_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Alma API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Alma API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Alma sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class AlmaPaymentsView(APIView):
    """List user's Alma payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = AlmaPayment.objects.filter(user=request.user).select_related('connection')

        # Filter by state
        state = request.query_params.get('state')
        if state:
            qs = qs.filter(state=state)

        # Filter by kind
        kind = request.query_params.get('kind')
        if kind:
            qs = qs.filter(kind=kind)

        serializer = AlmaPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)
