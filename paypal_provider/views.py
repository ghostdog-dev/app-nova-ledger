import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PayPalConnection, PayPalDispute, PayPalInvoice, PayPalTransaction
from .serializers import (
    PayPalConnectionSerializer,
    PayPalDisputeSerializer,
    PayPalInvoiceSerializer,
    PayPalTransactionSerializer,
)
from .services.paypal_sync import sync_paypal_data

logger = logging.getLogger(__name__)

SANDBOX_API_BASE = 'https://api-m.sandbox.paypal.com'
LIVE_API_BASE = 'https://api-m.paypal.com'


class PayPalConnectView(APIView):
    """Connect PayPal using API key credentials (client_id + client_secret)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        client_id = request.data.get('client_id', '').strip()
        client_secret = request.data.get('client_secret', '').strip()
        is_sandbox = request.data.get('is_sandbox', True)

        if not client_id or not client_secret:
            return Response(
                {'error': 'client_id and client_secret are required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials by requesting an access token
        api_base = SANDBOX_API_BASE if is_sandbox else LIVE_API_BASE
        try:
            token_resp = httpx.post(
                f'{api_base}/v1/oauth2/token',
                auth=(client_id, client_secret),
                data={'grant_type': 'client_credentials'},
                headers={'Accept': 'application/json'},
                timeout=30,
            )
            token_resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.warning('PayPal credential verification failed: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': 'Invalid PayPal credentials. Please check your client_id and client_secret.'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Unexpected error verifying PayPal credentials')
            return Response(
                {'error': 'Failed to verify PayPal credentials'},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        # Store connection
        connection, created = PayPalConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'client_id': client_id,
                'client_secret': client_secret,
                'is_sandbox': is_sandbox,
                'is_active': True,
            },
        )

        action = 'connected' if created else 'updated'
        logger.info('PayPal %s for user %s (sandbox=%s)', action, request.user.email, is_sandbox)

        serializer = PayPalConnectionSerializer(connection)
        return Response({
            'status': action,
            'connection': serializer.data,
        }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class PayPalDisconnectView(APIView):
    """Disconnect PayPal -- deactivate the connection."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            connection = request.user.paypal_connection
        except PayPalConnection.DoesNotExist:
            return Response({'error': 'No PayPal connection found'}, status=status.HTTP_404_NOT_FOUND)

        connection.is_active = False
        connection.save(update_fields=['is_active'])
        return Response({'status': 'disconnected'})


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
