import logging
import secrets
from datetime import timedelta
from urllib.parse import urlencode

from django.conf import settings as django_settings
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import httpx

from .models import (
    MollieConnection,
    MollieInvoice,
    MolliePayment,
    MollieRefund,
    MollieSettlement,
)
from .serializers import (
    MollieInvoiceSerializer,
    MolliePaymentSerializer,
    MollieRefundSerializer,
    MollieSettlementSerializer,
)
from .services.mollie_sync import MollieClient, sync_mollie_data

logger = logging.getLogger(__name__)

MOLLIE_AUTHORIZE_URL = 'https://my.mollie.com/oauth2/authorize'
MOLLIE_TOKEN_URL = 'https://api.mollie.com/oauth2/tokens'
MOLLIE_SCOPES = 'organizations.read payments.read refunds.read settlements.read invoices.read'


class MollieConnectView(APIView):
    """Start the Mollie Connect OAuth2 flow -- returns an authorize URL."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        state = secrets.token_urlsafe(32)
        request.session['mollie_oauth_state'] = state

        params = {
            'client_id': django_settings.MOLLIE_CLIENT_ID,
            'redirect_uri': django_settings.MOLLIE_REDIRECT_URI,
            'response_type': 'code',
            'scope': MOLLIE_SCOPES,
            'state': state,
        }
        authorize_url = f'{MOLLIE_AUTHORIZE_URL}?{urlencode(params)}'

        return Response({'authorize_url': authorize_url})


class MollieCallbackView(View):
    """Handle OAuth2 callback from Mollie. No DRF auth -- external redirect."""

    def get(self, request):
        error = request.GET.get('error')
        if error:
            error_desc = request.GET.get('error_description', error)
            logger.warning('Mollie OAuth callback error: %s — %s', error, error_desc)
            return redirect(f'/emails/test/?mollie_error={error}')

        code = request.GET.get('code', '')
        state = request.GET.get('state', '')

        if not code:
            logger.warning('Mollie callback missing code')
            return redirect('/emails/test/?mollie_error=missing_code')

        # Validate state
        user = request.user if request.user.is_authenticated else None
        if not user:
            logger.warning('Mollie callback: no authenticated user in session')
            return redirect('/login/?next=/emails/test/&mollie_error=not_authenticated')

        expected_state = request.session.pop('mollie_oauth_state', None)
        if not expected_state or state != expected_state:
            logger.warning('Mollie callback: state mismatch (CSRF check failed)')
            return redirect('/emails/test/?mollie_error=state_mismatch')

        # Exchange code for tokens
        try:
            token_resp = httpx.post(
                MOLLIE_TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': django_settings.MOLLIE_REDIRECT_URI,
                },
                auth=(django_settings.MOLLIE_CLIENT_ID, django_settings.MOLLIE_CLIENT_SECRET),
                timeout=30.0,
            )
            token_resp.raise_for_status()
            token_data = token_resp.json()
        except httpx.HTTPStatusError as e:
            logger.error('Mollie token exchange failed: %s %s', e.response.status_code, e.response.text)
            return redirect('/emails/test/?mollie_error=token_exchange_failed')
        except Exception:
            logger.exception('Unexpected error during Mollie token exchange')
            return redirect('/emails/test/?mollie_error=token_exchange_error')

        access_token = token_data['access_token']
        refresh_token = token_data.get('refresh_token', '')
        expires_in = token_data.get('expires_in', 3600)
        token_expires_at = timezone.now() + timedelta(seconds=expires_in)

        # Fetch organization info
        org_id = ''
        org_name = ''
        try:
            org_resp = httpx.get(
                'https://api.mollie.com/v2/organizations/me',
                headers={'Authorization': f'Bearer {access_token}'},
                timeout=30.0,
            )
            org_resp.raise_for_status()
            org_data = org_resp.json()
            org_id = org_data.get('id', '')
            org_name = org_data.get('name', '')
        except Exception:
            logger.exception('Failed to fetch Mollie organization info')

        # Store connection
        MollieConnection.objects.update_or_create(
            user=user,
            defaults={
                'access_token': access_token,
                'refresh_token': refresh_token,
                'token_expires_at': token_expires_at,
                'organization_id': org_id,
                'organization_name': org_name,
                'is_active': True,
            },
        )
        logger.info('Mollie connected for user %s (org: %s)', user.email, org_name)

        return redirect('/emails/test/?mollie_connected=true')


class MollieSyncView(APIView):
    """Trigger a manual Mollie data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_mollie_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Mollie API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Mollie API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Mollie sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class MolliePaymentsView(APIView):
    """List user's Mollie payments with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MolliePayment.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        payment_status = request.query_params.get('status')
        if payment_status:
            qs = qs.filter(status=payment_status)

        # Filter by method
        method = request.query_params.get('method')
        if method:
            qs = qs.filter(method=method)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(created_at_mollie__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(created_at_mollie__lte=date_to)

        serializer = MolliePaymentSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieRefundsView(APIView):
    """List user's Mollie refunds."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieRefund.objects.filter(user=request.user).select_related('connection')

        refund_status = request.query_params.get('status')
        if refund_status:
            qs = qs.filter(status=refund_status)

        serializer = MollieRefundSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieSettlementsView(APIView):
    """List user's Mollie settlements."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieSettlement.objects.filter(user=request.user).select_related('connection')

        settlement_status = request.query_params.get('status')
        if settlement_status:
            qs = qs.filter(status=settlement_status)

        serializer = MollieSettlementSerializer(qs[:500], many=True)
        return Response(serializer.data)


class MollieInvoicesView(APIView):
    """List user's Mollie invoices."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = MollieInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by status
        invoice_status = request.query_params.get('status')
        if invoice_status:
            qs = qs.filter(status=invoice_status)

        serializer = MollieInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)
