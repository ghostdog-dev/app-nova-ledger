import logging

import stripe as stripe_lib
from django.conf import settings as django_settings
from django.shortcuts import redirect
from django.views import View
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
    """Connect Stripe using API secret key (sk_test_ or sk_live_)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        api_key = request.data.get('api_key', '')
        if not api_key or not api_key.startswith(('sk_test_', 'sk_live_', 'rk_test_', 'rk_live_')):
            return Response({'error': 'Invalid Stripe key. Must start with sk_test_ or sk_live_'}, status=400)

        try:
            stripe_lib.api_key = None  # reset global
            account = stripe_lib.Account.retrieve(api_key=api_key)
            name = ''
            if hasattr(account, 'business_profile') and account.business_profile:
                name = account.business_profile.get('name', '') or ''
            if not name and hasattr(account, 'settings') and account.settings:
                name = account.settings.get('dashboard', {}).get('display_name', '') or ''

            StripeConnection.objects.update_or_create(
                user=request.user,
                defaults={
                    'stripe_account_id': account.id,
                    'access_token': api_key,
                    'account_name': name,
                    'is_active': True,
                }
            )

            # Auto-sync
            try:
                sync_stripe_data(request.user)
            except Exception as e:
                logger.warning('Stripe auto-sync failed: %s', e)

            return Response({'connected': True, 'account_id': account.id, 'account_name': name})
        except stripe_lib.error.AuthenticationError:
            return Response({'error': 'Invalid API key'}, status=400)
        except Exception as e:
            return Response({'error': str(e)}, status=400)


    # StripeCallbackView removed — Stripe uses API key, not OAuth redirect


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
