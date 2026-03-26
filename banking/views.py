import logging

from django.conf import settings
from django.shortcuts import redirect
from django.views import View
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

import httpx

from .models import BankAccount, BankConnection, BankTransaction, PowensUser
from .serializers import BankAccountSerializer, BankConnectionSerializer, BankTransactionSerializer
from .services.powens_client import PowensClient
from .services.powens_sync import sync_bank_data

logger = logging.getLogger(__name__)


class BankConnectView(APIView):
    """Start the bank connection flow -- returns a webview URL."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # 1. Get or create PowensUser for this user
            try:
                powens_user = request.user.powens
                client = PowensClient(auth_token=powens_user.auth_token)
            except PowensUser.DoesNotExist:
                # Create a new Powens user
                client = PowensClient()
                result = client.create_user()
                powens_user = PowensUser.objects.create(
                    user=request.user,
                    powens_user_id=result['id_user'],
                    auth_token=result['auth_token'],
                )
                client.auth_token = powens_user.auth_token
                logger.info('Created Powens user %d for %s', powens_user.powens_user_id, request.user.email)

            # 2. Get temporary code for webview
            code_data = client.get_temporary_code()
            temp_code = code_data.get('code', '')

            # 3. Build webview URL
            webview_url = (
                f'https://webview.powens.com/connect'
                f'?domain={settings.POWENS_DOMAIN}'
                f'&client_id={settings.POWENS_CLIENT_ID}'
                f'&redirect_uri={settings.POWENS_REDIRECT_URI}'
                f'&code={temp_code}'
            )

            return Response({'webview_url': webview_url})

        except httpx.HTTPStatusError as e:
            logger.error('Powens API error during connect: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Powens API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during bank connect')
            return Response(
                {'error': 'Failed to start bank connection'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BankCallbackView(View):
    """Handle callback from Powens webview. No auth required (external redirect)."""

    def get(self, request):
        connection_id = request.GET.get('connection_id')
        error = request.GET.get('error')

        if error:
            logger.warning('Powens callback error: %s', error)
            return redirect('/emails/test/?banking_error=' + error)

        if not connection_id:
            logger.warning('Powens callback missing connection_id')
            return redirect('/emails/test/?banking_error=missing_connection_id')

        # Find the user from their session (they were logged in before redirect)
        user = request.user if request.user.is_authenticated else None

        if not user:
            logger.warning('Powens callback: no authenticated user in session')
            return redirect('/login/?next=/emails/test/&banking_error=not_authenticated')

        try:
            powens_user = user.powens
            client = PowensClient(auth_token=powens_user.auth_token)

            # Fetch connection details from Powens
            conn_data = client.get_connection(int(connection_id))

            BankConnection.objects.update_or_create(
                powens_connection_id=int(connection_id),
                defaults={
                    'user': user,
                    'bank_name': conn_data.get('connector', {}).get('name', ''),
                    'state': conn_data.get('state') or '',
                },
            )
            logger.info('Bank connection %s stored for user %s', connection_id, user.email)

            # Trigger initial sync
            try:
                sync_bank_data(user)
                logger.info('Initial bank sync completed for user %s', user.email)
            except Exception:
                logger.exception('Initial bank sync failed for user %s', user.email)

        except PowensUser.DoesNotExist:
            logger.error('Powens callback: user %s has no PowensUser', user.email)
            return redirect('/emails/test/?banking_error=no_powens_user')
        except httpx.HTTPStatusError as e:
            logger.error('Powens API error during callback: %s', e.response.status_code)
            return redirect('/emails/test/?banking_error=api_error')
        except Exception:
            logger.exception('Unexpected error during bank callback')
            return redirect('/emails/test/?banking_error=unexpected_error')

        return redirect('/emails/test/?banking_connected=true')


class BankSyncView(APIView):
    """Trigger a manual bank sync."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            stats = sync_bank_data(request.user)
            return Response(stats)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except httpx.HTTPStatusError as e:
            logger.error('Powens API error during sync: %s %s', e.response.status_code, e.response.text)
            return Response(
                {'error': f'Powens API error: {e.response.status_code}'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            logger.exception('Unexpected error during bank sync')
            return Response(
                {'error': 'Sync failed'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class BankAccountsView(APIView):
    """List user's bank accounts."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        accounts = BankAccount.objects.filter(user=request.user).select_related('connection')
        serializer = BankAccountSerializer(accounts, many=True)
        return Response(serializer.data)


class BankTransactionsView(APIView):
    """List user's bank transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = BankTransaction.objects.filter(user=request.user).select_related('account')

        # Filter by account
        account_id = request.query_params.get('account_id')
        if account_id:
            qs = qs.filter(account_id=account_id)

        # Filter by date range
        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        # Filter by amount range
        min_amount = request.query_params.get('min_amount')
        if min_amount:
            qs = qs.filter(value__gte=min_amount)

        max_amount = request.query_params.get('max_amount')
        if max_amount:
            qs = qs.filter(value__lte=max_amount)

        # Filter pending
        coming = request.query_params.get('coming')
        if coming is not None:
            qs = qs.filter(coming=coming.lower() in ('true', '1'))

        serializer = BankTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class BankCorrelateView(APIView):
    """Trigger bank-email transaction correlation."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.correlation import correlate_providers, correlate_transactions
        bank_stats = correlate_transactions(request.user)
        provider_stats = correlate_providers(request.user)
        return Response({**bank_stats, **provider_stats})


class BankEnrichView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .services.enrichment import enrich_transactions
        force = request.data.get('force', False)
        stats = enrich_transactions(request.user, force=force)
        return Response(stats)


class BankSummaryView(APIView):
    """Monthly accounting summary."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .services.summary import monthly_summary
        year = request.query_params.get('year')
        month = request.query_params.get('month')
        if year and month:
            data = monthly_summary(request.user, int(year), int(month))
        else:
            data = monthly_summary(request.user)
        return Response(data)


class BankDisconnectView(APIView):
    """Disconnect a bank connection."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, connection_id):
        try:
            connection = BankConnection.objects.get(
                id=connection_id, user=request.user
            )
        except BankConnection.DoesNotExist:
            return Response(
                {'error': 'Connection not found'},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Delete on Powens
        try:
            powens_user = request.user.powens
            client = PowensClient(auth_token=powens_user.auth_token)
            client.delete_connection(connection.powens_connection_id)
            logger.info('Deleted connection %d on Powens', connection.powens_connection_id)
        except PowensUser.DoesNotExist:
            logger.warning('No PowensUser for %s — deleting locally only', request.user.email)
        except httpx.HTTPStatusError as e:
            logger.error(
                'Failed to delete connection on Powens: %s — deleting locally anyway',
                e.response.status_code,
            )
        except Exception:
            logger.exception('Error deleting connection on Powens — deleting locally anyway')

        # Delete locally (cascades to accounts and transactions)
        connection.delete()
        return Response({'status': 'disconnected'})
