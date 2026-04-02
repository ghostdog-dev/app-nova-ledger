import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FintectureConnection, FintecturePayment, FintectureSettlement
from .serializers import (
    FintecturePaymentSerializer,
    FintectureSettlementSerializer,
)
from .services.fintecture_sync import FintectureClient, sync_fintecture_data

logger = logging.getLogger(__name__)


class FintectureConnectView(APIView):
    """Connect Fintecture via app_id + app_secret. Validates by requesting an access token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        app_id = request.data.get('app_id', '').strip()
        app_secret = request.data.get('app_secret', '').strip()
        is_sandbox = request.data.get('is_sandbox', True)
        account_name = request.data.get('account_name', '').strip()

        if not app_id or not app_secret:
            return Response({'error': 'app_id and app_secret required'}, status=status.HTTP_400_BAD_REQUEST)

        # Verify credentials by requesting an access token
        try:
            client = FintectureClient(app_id, app_secret, is_sandbox=is_sandbox)
            client._get_access_token()
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Fintecture API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Fintecture API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Fintecture credentials')
            return Response({'error': 'Failed to verify credentials'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        FintectureConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'app_id': app_id,
                'app_secret': app_secret,
                'is_sandbox': is_sandbox,
                'account_name': account_name,
                'is_active': True,
            },
        )
        logger.info('Fintecture connected for user %s (sandbox=%s)', request.user.email, is_sandbox)

        return Response({
            'status': 'connected',
            'is_sandbox': is_sandbox,
            'account_name': account_name,
        })


class FintectureSyncView(APIView):
    """Trigger a manual Fintecture data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_fintecture_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Fintecture API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Fintecture API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Fintecture sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class FintecturePaymentsView(APIView):
    """List user's Fintecture payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = FintecturePayment.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        payment_status = request.query_params.get('status')
        if payment_status:
            qs = qs.filter(status=payment_status)

        # Filter by transfer_state
        transfer_state = request.query_params.get('transfer_state')
        if transfer_state:
            qs = qs.filter(transfer_state=transfer_state)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(execution_date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(execution_date__lte=date_to)

        serializer = FintecturePaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class FintectureSettlementsView(APIView):
    """List user's Fintecture settlements."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = FintectureSettlement.objects.filter(user=request.user).select_related('connection')

        settlement_status = request.query_params.get('status')
        if settlement_status:
            qs = qs.filter(status=settlement_status)

        serializer = FintectureSettlementSerializer(qs[:500], many=True)
        return Response(serializer.data)
