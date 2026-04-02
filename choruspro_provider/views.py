import logging

import httpx
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ChorusProConnection, ChorusProInvoice
from .serializers import ChorusProInvoiceSerializer
from .services.choruspro_sync import ChorusProClient, sync_choruspro_data

logger = logging.getLogger(__name__)


class ChorusProConnectView(APIView):
    """Connect Chorus Pro via client credentials. User provides client_id, client_secret,
    technical_user_id, and structure_id."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        client_id = request.data.get('client_id', '').strip()
        client_secret = request.data.get('client_secret', '').strip()
        technical_user_id = request.data.get('technical_user_id')
        structure_id = request.data.get('structure_id')
        is_sandbox = request.data.get('is_sandbox', True)

        # Validate required fields
        if not client_id or not client_secret:
            return Response(
                {'error': 'client_id and client_secret required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if technical_user_id is None or structure_id is None:
            return Response(
                {'error': 'technical_user_id and structure_id required'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            technical_user_id = int(technical_user_id)
            structure_id = int(structure_id)
        except (TypeError, ValueError):
            return Response(
                {'error': 'technical_user_id and structure_id must be integers'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Verify credentials by requesting a token
        try:
            client = ChorusProClient(
                client_id=client_id,
                client_secret=client_secret,
                technical_user_id=technical_user_id,
                structure_id=structure_id,
                is_sandbox=is_sandbox,
            )
            client._get_token()
            client.close()
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return Response({'error': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)
            logger.error('Chorus Pro OAuth error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Chorus Pro OAuth error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error verifying Chorus Pro credentials')
            return Response(
                {'error': 'Failed to verify credentials'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Store connection
        ChorusProConnection.objects.update_or_create(
            user=request.user,
            defaults={
                'client_id': client_id,
                'client_secret': client_secret,
                'technical_user_id': technical_user_id,
                'structure_id': structure_id,
                'is_sandbox': is_sandbox,
                'is_active': True,
            },
        )
        env = 'sandbox' if is_sandbox else 'production'
        logger.info('Chorus Pro connected for user %s (%s, structure=%s)', request.user.email, env, structure_id)

        return Response({
            'status': 'connected',
            'environment': env,
            'technical_user_id': technical_user_id,
            'structure_id': structure_id,
        })


class ChorusProSyncView(APIView):
    """Trigger a manual Chorus Pro data sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        date_from = request.data.get('date_from')
        date_to = request.data.get('date_to')

        try:
            stats = sync_choruspro_data(request.user, date_from=date_from, date_to=date_to)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Chorus Pro API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Chorus Pro API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during Chorus Pro sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class ChorusProInvoicesView(APIView):
    """List user's Chorus Pro invoices with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ChorusProInvoice.objects.filter(user=request.user).select_related('connection')

        # Filter by type_facture
        type_facture = request.query_params.get('type_facture')
        if type_facture:
            qs = qs.filter(type_facture=type_facture)

        # Filter by statut
        statut = request.query_params.get('statut')
        if statut:
            qs = qs.filter(statut=statut)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date_depot__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date_depot__lte=date_to)

        serializer = ChorusProInvoiceSerializer(qs[:500], many=True)
        return Response(serializer.data)
