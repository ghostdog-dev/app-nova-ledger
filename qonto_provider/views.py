import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import QontoBankAccount, QontoConnection, QontoTransaction
from .serializers import QontoBankAccountSerializer, QontoTransactionSerializer
from .services.qonto_sync import QontoClient, sync_qonto_data

logger = logging.getLogger(__name__)


class QontoConnectView(APIView):
    """Connect Qonto via login (org slug) + secret_key."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        login = request.data.get('login', '').strip()
        secret_key = request.data.get('secret_key', '').strip()

        if not login or not secret_key:
            return Response(
                {'error': 'login and secret_key required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials by calling GET /v2/organization
        org_name = ''
        try:
            client = QontoClient(login, secret_key)
            org_data = client.get_organization()
            organization = org_data.get('organization', {})
            org_name = organization.get('name', '')
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Qonto API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Qonto API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Qonto credentials')
            return Response({'error': 'Failed to verify credentials'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        # Store connection
        QontoConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'login': login,
                'secret_key': secret_key,
                'organization_name': org_name,
                'is_active': True,
            },
        )
        logger.info('Qonto connected for user %s (org: %s)', request.user.email, org_name)

        return Response({
            'status': 'connected',
            'organization_name': org_name,
        })


class QontoSyncView(APIView):
    """Trigger a manual Qonto data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_qonto_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Qonto API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Qonto API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Qonto sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class QontoBankAccountsView(APIView):
    """List user's Qonto bank accounts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = QontoBankAccount.objects.filter(user=request.user).select_related('connection')
        serializer = QontoBankAccountSerializer(qs[:500], many=True)
        return Response(serializer.data)


class QontoTransactionsView(APIView):
    """List user's Qonto transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = QontoTransaction.objects.filter(user=request.user).select_related('connection')

        # Filter by side (credit / debit)
        side = request.query_params.get('side')
        if side:
            qs = qs.filter(side=side)

        # Filter by status (pending / declined / completed)
        tx_status = request.query_params.get('status')
        if tx_status:
            qs = qs.filter(status=tx_status)

        # Filter by operation_type
        operation_type = request.query_params.get('operation_type')
        if operation_type:
            qs = qs.filter(operation_type=operation_type)

        # Filter by date range (settled_at)
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(settled_at__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(settled_at__lte=date_to)

        serializer = QontoTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)
