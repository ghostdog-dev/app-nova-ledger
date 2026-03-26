import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import httpx

from .models import PayPalConnection, PayPalInvoice, PayPalTransaction
from .serializers import (
    PayPalConnectInputSerializer,
    PayPalConnectionSerializer,
    PayPalInvoiceSerializer,
    PayPalTransactionSerializer,
)
from .services.paypal_sync import PayPalClient, sync_paypal_data

logger = logging.getLogger(__name__)


class PayPalConnectView(APIView):
    """Connect a PayPal account by providing client_id + client_secret."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = PayPalConnectInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_id = serializer.validated_data['client_id']
        client_secret = serializer.validated_data['client_secret']
        is_sandbox = serializer.validated_data['is_sandbox']

        # Verify credentials by attempting to get an access token
        temp_connection = PayPalConnection(
            user=request.user,
            client_id=client_id,
            client_secret=client_secret,
            is_sandbox=is_sandbox,
        )
        client = PayPalClient(temp_connection)

        try:
            user_info = client.verify_credentials()
            account_email = ''
            emails = user_info.get('emails', [])
            for email_info in emails:
                if email_info.get('primary'):
                    account_email = email_info.get('value', '')
                    break
            if not account_email and emails:
                account_email = emails[0].get('value', '')
        except httpx.HTTPStatusError as e:
            logger.error('PayPal credential verification failed: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': 'Invalid PayPal credentials'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception('Unexpected error verifying PayPal credentials')
            return Response(
                {'error': 'Failed to verify PayPal credentials'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Create or update the connection
        connection, created = PayPalConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'client_id': client_id,
                'client_secret': client_secret,
                'account_email': account_email,
                'is_sandbox': is_sandbox,
                'is_active': True,
            },
        )

        action = 'connected' if created else 'updated'
        logger.info('PayPal %s for user %s (email: %s)', action, request.user.email, account_email)

        return Response({
            'status': action,
            'connection': PayPalConnectionSerializer(connection).data,
        })


class PayPalSyncView(APIView):
    """Trigger a manual PayPal sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        days_back = int(request.data.get('days_back', 30))

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
