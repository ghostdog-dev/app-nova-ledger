"""Monthly accounting summary for bank transactions."""
import logging
from collections import defaultdict
from decimal import Decimal
from django.db.models import Sum, Count, Q

from banking.models import BankTransaction, TransactionMatch

logger = logging.getLogger(__name__)


def monthly_summary(user, year=None, month=None):
    """
    Generate monthly accounting summary.
    If year/month not specified, returns summary for all available months.
    """
    from django.utils import timezone

    if year and month:
        txs = BankTransaction.objects.filter(
            user=user, date__year=year, date__month=month, coming=False
        )
        months = [(year, month)]
    else:
        # Get all distinct year-months
        txs = BankTransaction.objects.filter(user=user, coming=False)
        dates = txs.dates('date', 'month', order='DESC')
        months = [(d.year, d.month) for d in dates]

    summaries = []
    for y, m in months:
        month_txs = txs.filter(date__year=y, date__month=m)

        # Basic totals
        income = month_txs.filter(value__gt=0).aggregate(
            total=Sum('value'), count=Count('id'))
        expenses = month_txs.filter(value__lt=0).aggregate(
            total=Sum('value'), count=Count('id'))

        # By category
        by_category = defaultdict(lambda: {'total': Decimal('0'), 'count': 0, 'label': ''})
        for tx in month_txs.filter(value__lt=0):
            cat = tx.expense_category or 'uncategorized'
            by_category[cat]['total'] += abs(tx.value)
            by_category[cat]['count'] += 1
            by_category[cat]['label'] = tx.expense_category_label or 'Non classe'

        # Business vs Personal
        business = month_txs.filter(value__lt=0, business_personal='business').aggregate(total=Sum('value'))
        personal = month_txs.filter(value__lt=0, business_personal='personal').aggregate(total=Sum('value'))
        unknown = month_txs.filter(value__lt=0).filter(
            Q(business_personal='unknown') | Q(business_personal='')
        ).aggregate(total=Sum('value'))

        # TVA
        tva_deductible = month_txs.filter(value__lt=0, tva_deductible=True).aggregate(total=Sum('value'))
        tva_non_deductible = month_txs.filter(value__lt=0, tva_deductible=False).aggregate(total=Sum('value'))

        # Matched vs unmatched
        matched_count = TransactionMatch.objects.filter(
            user=user, bank_transaction__date__year=y, bank_transaction__date__month=m
        ).exclude(status='rejected').count()

        # Recurring
        recurring = month_txs.filter(is_recurring=True, value__lt=0).aggregate(
            total=Sum('value'), count=Count('id'))

        summaries.append({
            'year': y,
            'month': m,
            'income': {
                'total': str(income['total'] or 0),
                'count': income['count'] or 0,
            },
            'expenses': {
                'total': str(abs(expenses['total'] or 0)),
                'count': expenses['count'] or 0,
            },
            'by_category': {
                cat: {'total': str(data['total']), 'count': data['count'], 'label': data['label']}
                for cat, data in sorted(by_category.items(), key=lambda x: -x[1]['total'])
            },
            'business_total': str(abs(business['total'] or 0)),
            'personal_total': str(abs(personal['total'] or 0)),
            'unknown_total': str(abs(unknown['total'] or 0)),
            'tva_deductible_total': str(abs(tva_deductible['total'] or 0)),
            'tva_non_deductible_total': str(abs(tva_non_deductible['total'] or 0)),
            'matched_with_email': matched_count,
            'total_transactions': month_txs.count(),
            'recurring': {
                'total': str(abs(recurring['total'] or 0)),
                'count': recurring['count'] or 0,
            },
        })

    return summaries
