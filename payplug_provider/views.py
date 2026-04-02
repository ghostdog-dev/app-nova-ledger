import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PayPlugConnection, PayPlugPayment, PayPlugRefund
from .serializers import PayPlugPaymentSerializer, PayPlugRefundSerializer
from .services.payplug_sync import PayPlugClient, sync_payplug_data

logger = logging.getLogger(__name__)


class PayPlugConnectView(APIView):
    """Connect PayPlug via secret key. User provides sk_test_... or sk_live_... key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        secret_key = request.data.get('secret_key', '').strip()
        if not secret_key:
            return Response({'error': 'secret_key required'}, status=status.HTTP_400_BAD_REQUEST)

        if not secret_key.startswith(('sk_test_', 'sk_live_')):
            return Response(
                {'error': 'Invalid secret key format. Must start with sk_test_ or sk_live_'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        is_live = secret_key.startswith('sk_live_')

        # Verify key by listing 1 payment
        try:
            client = PayPlugClient(secret_key)
            client.verify_key()
        except Exception as e:
            error_str = str(e)
            if '401' in error_str or 'Unauthorized' in error_str:
                return Response({'error': 'Invalid secret key'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('PayPlug API error during connect: %s', error_str)
            return Response(
                {'error': f'PayPlug API error: {error_str}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Store connection
        PayPlugConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'secret_key': secret_key,
                'is_live': is_live,
                'account_name': f'{"Live" if is_live else "Test"} account',
                'is_active': True,
            },
        )
        logger.info('PayPlug connected for user %s (live=%s)', request.user.email, is_live)

        return Response({
            'status': 'connected',
            'is_live': is_live,
            'key_type': 'live' if is_live else 'test',
        })


class PayPlugSyncView(APIView):
    """Trigger a manual PayPlug data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_payplug_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Unexpected error during PayPlug sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PayPlugPaymentsView(APIView):
    """List user's PayPlug payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PayPlugPayment.objects.filter(user=request.user).select_related('connection')

        # Filter by status (is_paid)
        payment_status = request.query_params.get('status')
        if payment_status == 'paid':
            qs = qs.filter(is_paid=True)
        elif payment_status == 'unpaid':
            qs = qs.filter(is_paid=False)
        elif payment_status == 'refunded':
            qs = qs.filter(is_refunded=True)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at_payplug__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at_payplug__lte=date_to)

        serializer = PayPlugPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PayPlugRefundsView(APIView):
    """List user's PayPlug refunds."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PayPlugRefund.objects.filter(user=request.user).select_related('connection')

        serializer = PayPlugRefundSerializer(qs[:500], many=True)
        return Response(serializer.data)
