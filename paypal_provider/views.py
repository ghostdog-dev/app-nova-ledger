import logging
from datetime import timedelta

from django.conf import settings as s
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import httpx

from .models import PayPalConnection, PayPalDispute, PayPalInvoice, PayPalTransaction
from .serializers import (
    PayPalConnectionSerializer,
    PayPalDisputeSerializer,
    PayPalInvoiceSerializer,
    PayPalTransactionSerializer,
)
from .services.paypal_sync import sync_paypal_data

logger = logging.getLogger(__name__)

SANDBOX_BASE = 'https://www.sandbox.paypal.com'
LIVE_BASE = 'https://www.paypal.com'
SANDBOX_API_BASE = 'https://api-m.sandbox.paypal.com'
LIVE_API_BASE = 'https://api-m.paypal.com'


class PayPalConnectView(APIView):
    """Start PayPal OAuth flow -- returns authorize URL."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        base = SANDBOX_BASE if s.PAYPAL_SANDBOX else LIVE_BASE
        authorize_url = (
            f'{base}/signin/authorize'
            f'?flowEntry=static'
            f'&client_id={s.PAYPAL_CLIENT_ID}'
            f'&response_type=code'
            f'&scope=openid email https://uri.paypal.com/services/reporting/search/read'
            f'&redirect_uri={s.PAYPAL_REDIRECT_URI}'
        )
        return Response({'authorize_url': authorize_url})


class PayPalCallbackView(View):
    """Handle OAuth callback from PayPal. No DRF auth -- external redirect."""

    def get(self, request):
        code = request.GET.get('code')
        error = request.GET.get('error')

        if error:
            logger.warning('PayPal callback error: %s', error)
            return redirect('/emails/test/?paypal_error=' + error)

        if not code:
            logger.warning('PayPal callback missing code')
            return redirect('/emails/test/?paypal_error=missing_code')

        user = request.user if request.user.is_authenticated else None
        if not user:
            logger.warning('PayPal callback: no authenticated user in session')
            return redirect('/login/?next=/emails/test/&paypal_error=not_authenticated')

        api_base = SANDBOX_API_BASE if s.PAYPAL_SANDBOX else LIVE_API_BASE

        # 1. Exchange authorization code for tokens
        try:
            token_resp = httpx.post(
                f'{api_base}/v1/oauth2/token',
                auth=(s.PAYPAL_CLIENT_ID, s.PAYPAL_CLIENT_SECRET),
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                },
                headers={'Accept': 'application/json'},
                timeout=30,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except httpx.HTTPStatusError as e:
            logger.error('PayPal token exchange failed: %s %s', e.response.status_code, e.response.text)
            return redirect('/emails/test/?paypal_error=token_exchange_failed')
        except Exception:
            logger.exception('Unexpected error during PayPal token exchange')
            return redirect('/emails/test/?paypal_error=token_exchange_error')

        access_token = token_data.get('access_token', '')
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 28800)
        token_expires_at = timezone.now() + timedelta(seconds=expires_in)

        # 2. Fetch user info
        paypal_user_id = ''
        account_email = ''
        try:
            userinfo_resp = httpx.get(
                f'{api_base}/v1/identity/oauth2/userinfo?schema=paypalv1.2',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=30,
            )
            userinfo_resp.raise_for_status()
            userinfo = userinfo_resp.json()

            paypal_user_id = userinfo.get('payer_id', '') or userinfo.get('user_id', '')

            emails = userinfo.get('emails', [])
            for email_info in emails:
                if email_info.get('primary'):
                    account_email = email_info.get('value', '')
                    break
            if not account_email and emails:
                account_email = emails[0].get('value', '')
        except Exception:
            logger.exception('Failed to fetch PayPal user info (tokens stored anyway)')

        # 3. Store connection
        connection, created = PayPalConnection.objects.update_or_create(
            user=user,
            defaults={
                'paypal_user_id': paypal_user_id,
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expires_at': token_expires_at,
                'account_email': account_email,
                'is_sandbox': s.PAYPAL_SANDBOX,
                'is_active': True,
            },
        )

        action = 'connected' if created else 'updated'
        logger.info('PayPal %s for user %s (email: %s)', action, user.email, account_email)

        return redirect('/emails/test/?paypal_connected=true')


class PayPalSyncView(APIView):
    """Trigger a manual PayPal sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            days_back = min(int(request.data.get('days_back', 30)), 365)
        except (ValueError, TypeError):
            days_back = 30

        try:
            stats = sync_paypal_data(request.user, days_back=days_back)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('PayPal API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'PayPal API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during PayPal sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PayPalTransactionsView(APIView):
    """List user's PayPal transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PayPalTransaction.objects.filter(user=request.user).select_related('connection')

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(initiation_date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(initiation_date__lte=date_to)

        # Filter by status
        tx_status = request.query_params.get('status')
        if tx_status:
            qs = qs.filter(transaction_status=tx_status)

        # Filter by event code
        event_code = request.query_params.get('event_code')
        if event_code:
            qs = qs.filter(event_code=event_code)

        # Filter by payer
        payer = request.query_params.get('payer')
        if payer:
            qs = qs.filter(payer_email__icontains=payer)

        serializer = PayPalTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PayPalInvoicesView(APIView):
    """List user's PayPal invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PayPalInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        inv_status = request.query_params.get('status')
        if inv_status:
            qs = qs.filter(status=inv_status)

        # Filter by recipient
        recipient = request.query_params.get('recipient')
        if recipient:
            qs = qs.filter(recipient_email__icontains=recipient)

        serializer = PayPalInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)


class PayPalDisputesView(APIView):
    """List user's PayPal disputes with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = PayPalDispute.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        dispute_status = request.query_params.get('status')
        if dispute_status:
            qs = qs.filter(status=dispute_status)

        # Filter by reason
        reason = request.query_params.get('reason')
        if reason:
            qs = qs.filter(reason=reason)

        serializer = PayPalDisputeSerializer(qs[:500], many=True)
        return Response(serializer.data)
