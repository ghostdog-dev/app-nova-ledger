import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    GoCardlessConnection,
    GoCardlessMandate,
    GoCardlessPayment,
    GoCardlessPayout,
    GoCardlessRefund,
    GoCardlessSubscription,
)
from .serializers import (
    GoCardlessMandateSerializer,
    GoCardlessPaymentSerializer,
    GoCardlessPayoutSerializer,
    GoCardlessRefundSerializer,
    GoCardlessSubscriptionSerializer,
)
from .services.gocardless_sync import GoCardlessClient, sync_gocardless_data

logger = logging.getLogger(__name__)


class GoCardlessConnectView(APIView):
    """Connect GoCardless via access token."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        access_token = request.data.get('access_token', '').strip()
        if not access_token:
            return Response({'error': 'access_token required'}, status=status.HTTP_400_BAD_REQUEST)

        environment = request.data.get('environment', 'sandbox').strip()
        if environment not in ('sandbox', 'live'):
            return Response(
                {'error': 'environment must be sandbox or live'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify token by listing 1 payment
        try:
            client = GoCardlessClient(access_token, environment)
            client.verify_token()
        except Exception as e:
            error_msg = str(e)
            if '401' in error_msg or 'unauthorized' in error_msg.lower():
                return Response({'error': 'Invalid access token'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('GoCardless API error during connect: %s', error_msg)
            return Response(
                {'error': f'GoCardless API error: {error_msg}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Store connection
        GoCardlessConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'access_token': access_token,
                'environment': environment,
                'is_active': True,
            },
        )
        logger.info('GoCardless connected for user %s (env: %s)', request.user.email, environment)

        return Response({
            'status': 'connected',
            'environment': environment,
        })


class GoCardlessSyncView(APIView):
    """Trigger a manual GoCardless data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_gocardless_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Unexpected error during GoCardless sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GoCardlessPaymentsView(APIView):
    """List user's GoCardless payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GoCardlessPayment.objects.filter(user=request.user).select_related('connection')

        payment_status = request.query_params.get('status')
        if payment_status:
            qs = qs.filter(status=payment_status)

        scheme = request.query_params.get('scheme')
        if scheme:
            qs = qs.filter(scheme=scheme)

        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at_gocardless__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at_gocardless__lte=date_to)

        serializer = GoCardlessPaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class GoCardlessMandatesView(APIView):
    """List user's GoCardless mandates."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GoCardlessMandate.objects.filter(user=request.user).select_related('connection')

        mandate_status = request.query_params.get('status')
        if mandate_status:
            qs = qs.filter(status=mandate_status)

        serializer = GoCardlessMandateSerializer(qs[:500], many=True)
        return Response(serializer.data)


class GoCardlessSubscriptionsView(APIView):
    """List user's GoCardless subscriptions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GoCardlessSubscription.objects.filter(user=request.user).select_related('connection')

        sub_status = request.query_params.get('status')
        if sub_status:
            qs = qs.filter(status=sub_status)

        serializer = GoCardlessSubscriptionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class GoCardlessPayoutsView(APIView):
    """List user's GoCardless payouts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GoCardlessPayout.objects.filter(user=request.user).select_related('connection')

        payout_status = request.query_params.get('status')
        if payout_status:
            qs = qs.filter(status=payout_status)

        serializer = GoCardlessPayoutSerializer(qs[:500], many=True)
        return Response(serializer.data)


class GoCardlessRefundsView(APIView):
    """List user's GoCardless refunds."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = GoCardlessRefund.objects.filter(user=request.user).select_related('connection')

        refund_status = request.query_params.get('status')
        if refund_status:
            qs = qs.filter(status=refund_status)

        serializer = GoCardlessRefundSerializer(qs[:500], many=True)
        return Response(serializer.data)
