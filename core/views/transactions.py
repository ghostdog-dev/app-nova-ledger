import math

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def transaction_list_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    empty_response = {
        'results': [],
        'count': 0,
        'page': 1,
        'page_size': 20,
        'total_pages': 0,
    }

    try:
        from banking.models import BankTransaction
    except (ImportError, Exception):
        return Response(empty_response)

    try:
        page = int(request.query_params.get('page', 1))
        page_size = int(request.query_params.get('page_size', 20))
    except (ValueError, TypeError):
        page = 1
        page_size = 20

    page = max(1, page)
    page_size = max(1, min(100, page_size))

    qs = BankTransaction.objects.filter(
        account__connection__user=request.user,
    ).select_related('account').order_by('-date')

    status_filter = request.query_params.get('status')
    if status_filter:
        if status_filter == 'pending':
            qs = qs.filter(coming=True)
        elif status_filter == 'completed':
            qs = qs.filter(coming=False)

    total_count = qs.count()
    total_pages = math.ceil(total_count / page_size) if total_count > 0 else 0
    offset = (page - 1) * page_size
    transactions = qs[offset:offset + page_size]

    results = [
        {
            'date': tx.date.isoformat(),
            'desc': tx.simplified_wording or tx.original_wording,
            'amount': str(tx.value),
            'status': 'pending' if tx.coming else 'completed',
            'source': tx.account.name if tx.account else '',
        }
        for tx in transactions
    ]

    return Response({
        'results': results,
        'count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': total_pages,
    })
