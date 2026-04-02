import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import FinancialAccount, FinancialTransaction
from .services.financial_connections import (
    create_fc_session,
    disconnect_account,
    process_linked_accounts,
    refresh_balances,
    refresh_ownership,
    refresh_transactions,
    subscribe_to_transactions,
    sync_all,
    sync_transactions,
)

logger = logging.getLogger(__name__)


# ============================================================
# API ENDPOINTS
# ============================================================

@login_required
@require_POST
def create_session_view(request):
    """Create a Financial Connections session for the auth modal."""
    try:
        result = create_fc_session(request.user)
        return JsonResponse(result)
    except Exception as e:
        logger.error('[FC] Session creation failed: %s', e)
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def link_accounts_view(request):
    """Process accounts after user completes the Stripe.js auth flow."""
    import json
    body = json.loads(request.body) if request.body else {}
    session_id = body.get('session_id', '')
    if not session_id:
        return JsonResponse({'error': 'session_id required'}, status=400)

    try:
        result = process_linked_accounts(request.user, session_id)
        return JsonResponse(result)
    except Exception as e:
        logger.error('[FC] Account linking failed: %s', e)
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def sync_view(request):
    """Sync all data (transactions, balances, ownership) for all linked accounts."""
    try:
        stats = sync_all(request.user)
        return JsonResponse(stats)
    except Exception as e:
        logger.error('[FC] Sync failed: %s', e)
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def subscribe_transactions_view(request, account_id):
    """Subscribe an account to daily transaction refreshes."""
    try:
        account = FinancialAccount.objects.get(
            stripe_account_id=account_id, user=request.user,
        )
        subscribe_to_transactions(account)
        return JsonResponse({'subscribed': True})
    except FinancialAccount.DoesNotExist:
        return JsonResponse({'error': 'Account not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def refresh_account_view(request, account_id):
    """Trigger on-demand refresh for transactions + balances + ownership."""
    try:
        account = FinancialAccount.objects.get(
            stripe_account_id=account_id, user=request.user,
        )
        results = {}
        permissions = account.permissions or []

        if 'transactions' in permissions:
            refresh_transactions(account)
            tx_stats = sync_transactions(account)
            results['transactions'] = tx_stats

        if 'balances' in permissions:
            bal = refresh_balances(account)
            results['balances'] = bal

        if 'ownership' in permissions:
            owners = refresh_ownership(account)
            results['ownership'] = owners

        return JsonResponse(results)
    except FinancialAccount.DoesNotExist:
        return JsonResponse({'error': 'Account not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


@login_required
@require_POST
def disconnect_view(request, account_id):
    """Disconnect a linked bank account."""
    try:
        account = FinancialAccount.objects.get(
            stripe_account_id=account_id, user=request.user,
        )
        disconnect_account(account)
        return JsonResponse({'disconnected': True})
    except FinancialAccount.DoesNotExist:
        return JsonResponse({'error': 'Account not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)


# ============================================================
# DATA ENDPOINTS (read-only, for exploring what we get)
# ============================================================

@login_required
def list_accounts_view(request):
    """List all linked financial accounts."""
    accounts = FinancialAccount.objects.filter(user=request.user)
    data = []
    for a in accounts:
        data.append({
            'id': a.stripe_account_id,
            'display_name': a.display_name,
            'institution': a.institution_name,
            'last4': a.last4,
            'category': a.category,
            'subcategory': a.subcategory,
            'status': a.status,
            'permissions': a.permissions,
            'balance_current': a.balance_current,
            'balance_available': a.balance_available,
            'balance_as_of': a.balance_as_of.isoformat() if a.balance_as_of else None,
            'ownership': a.ownership_data,
            'transaction_subscribed': a.transaction_subscribed,
            'transaction_count': a.transactions.count(),
            'created_at': a.created_at.isoformat(),
        })
    return JsonResponse({'accounts': data})


@login_required
def list_transactions_view(request, account_id):
    """List transactions for an account. Returns raw data for exploration."""
    try:
        account = FinancialAccount.objects.get(
            stripe_account_id=account_id, user=request.user,
        )
    except FinancialAccount.DoesNotExist:
        return JsonResponse({'error': 'Account not found'}, status=404)

    limit = int(request.GET.get('limit', 50))
    offset = int(request.GET.get('offset', 0))
    status_filter = request.GET.get('status', '')

    qs = FinancialTransaction.objects.filter(account=account)
    if status_filter:
        qs = qs.filter(status=status_filter)

    total = qs.count()
    txs = qs[offset:offset + limit]

    data = []
    for tx in txs:
        data.append({
            'id': tx.stripe_transaction_id,
            'amount': tx.amount,
            'amount_decimal': tx.amount_decimal,
            'currency': tx.currency,
            'description': tx.description,
            'status': tx.status,
            'transacted_at': tx.transacted_at.isoformat() if tx.transacted_at else None,
            'posted_at': tx.posted_at.isoformat() if tx.posted_at else None,
            'raw_data': tx.raw_data,
        })

    return JsonResponse({
        'account': account_id,
        'total': total,
        'offset': offset,
        'limit': limit,
        'transactions': data,
    })


# ============================================================
# TEST PAGE (dev only)
# ============================================================

@login_required
def test_page_view(request):
    """Dev test page for Financial Connections."""
    accounts = FinancialAccount.objects.filter(user=request.user)
    return render(request, 'stripe_financial/test.html', {
        'accounts': accounts,
    })
