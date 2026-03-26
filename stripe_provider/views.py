import logging

import stripe as stripe_lib
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import (
    StripeBalanceTransaction,
    StripeCharge,
    StripeConnection,
    StripeDispute,
    StripeInvoice,
    StripePayout,
    StripeSubscription,
)
from .serializers import (
    StripeBalanceTransactionSerializer,
    StripeChargeSerializer,
    StripeConnectionSerializer,
    StripeDisputeSerializer,
    StripeInvoiceSerializer,
    StripePayoutSerializer,
    StripeSubscriptionSerializer,
)
from .services.stripe_sync import sync_stripe_data

logger = logging.getLogger(__name__)


class StripeConnectView(APIView):
    """Connect a Stripe account by providing an API key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '').strip()
        if not api_key:
            return Response(
                {'error': 'api_key is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify the API key by retrieving the account
        try:
            account = stripe_lib.Account.retrieve(api_key=api_key)
        except stripe_lib.error.AuthenticationError:
            return Response(
                {'error': 'Invalid Stripe API key'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Failed to verify Stripe API key')
            return Response(
                {'error': 'Failed to verify Stripe API key'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        account_name = ''
        if hasattr(account, 'settings') and account.settings:
            dashboard = account.settings.get('dashboard', {})
            account_name = dashboard.get('display_name', '') or ''
        if not account_name and hasattr(account, 'business_profile') and account.business_profile:
            account_name = account.business_profile.get('name', '') or ''

        connection, created = StripeConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'stripe_account_id': account.id,
                'api_key': api_key,
                'account_name': account_name,
                'is_active': True,
            },
        )

        serializer = StripeConnectionSerializer(connection)
        return Response(
            serializer.data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class StripeSyncView(APIView):
    """Trigger a manual Stripe data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            days_back = min(int(request.data.get('days_back', 90)), 365)
        except (ValueError, TypeError):
            days_back = 90

        try:
            stats = sync_stripe_data(request.user, days_back=days_back)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Unexpected error during Stripe sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class StripeBalanceTransactionsView(APIView):
    """List Stripe balance transactions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripeBalanceTransaction.objects.filter(user=request.user).select_related('connection')

        # Filter by type
        txn_type = request.query_params.get('type')
        if txn_type:
            qs = qs.filter(type=txn_type)

        # Filter by status
        txn_status = request.query_params.get('status')
        if txn_status:
            qs = qs.filter(status=txn_status)

        serializer = StripeBalanceTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class StripeChargesView(APIView):
    """List Stripe charges."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripeCharge.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        charge_status = request.query_params.get('status')
        if charge_status:
            qs = qs.filter(status=charge_status)

        # Filter by customer
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        serializer = StripeChargeSerializer(qs[:500], many=True)
        return Response(serializer.data)


class StripePayoutsView(APIView):
    """List Stripe payouts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripePayout.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        payout_status = request.query_params.get('status')
        if payout_status:
            qs = qs.filter(status=payout_status)

        serializer = StripePayoutSerializer(qs[:500], many=True)
        return Response(serializer.data)


class StripeInvoicesView(APIView):
    """List Stripe invoices."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripeInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        # Filter by customer
        customer_id = request.query_params.get('customer_id')
        if customer_id:
            qs = qs.filter(customer_id=customer_id)

        serializer = StripeInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class StripeSubscriptionsView(APIView):
    """List Stripe subscriptions."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripeSubscription.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        sub_status = request.query_params.get('status')
        if sub_status:
            qs = qs.filter(status=sub_status)

        serializer = StripeSubscriptionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class StripeDisputesView(APIView):
    """List Stripe disputes."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = StripeDispute.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        dispute_status = request.query_params.get('status')
        if dispute_status:
            qs = qs.filter(status=dispute_status)

        serializer = StripeDisputeSerializer(qs[:500], many=True)
        return Response(serializer.data)
