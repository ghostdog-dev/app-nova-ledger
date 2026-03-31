from decimal import Decimal

from .base import BaseNormalizer


# Map email transaction types to unified categories
_TYPE_TO_CATEGORY = {
    'invoice': 'expense_service',
    'receipt': 'expense_goods',
    'order': 'expense_goods',
    'payment': 'other',
    'shipping': 'expense_shipping',
    'refund': 'refund',
    'cancellation': 'refund',
    'subscription': 'expense_service',
    'other': 'other',
}


class EmailNormalizer(BaseNormalizer):

    def normalize(self, user, tx) -> 'UnifiedTransaction':
        category = _TYPE_TO_CATEGORY.get(tx.type, 'other')
        amount = tx.amount if isinstance(tx.amount, Decimal) else (
            Decimal(str(tx.amount)) if tx.amount is not None else None
        )

        # Most email transactions are expenses (things the user bought)
        direction = 'outflow'
        if tx.type in ('refund', 'cancellation'):
            direction = 'inflow'

        reference = tx.invoice_number or tx.order_number or ''
        if tx.invoice_number and tx.order_number:
            reference = f'{tx.invoice_number} / {tx.order_number}'

        return self._build(
            user=user,
            source_type='email',
            source_id=f'email_tx_{tx.pk}',
            direction=direction,
            category=category,
            amount=amount,
            currency=(tx.currency or 'EUR').upper(),
            transaction_date=tx.transaction_date,
            vendor_name=tx.vendor_name or '',
            description=tx.description or '',
            reference=reference,
            payment_method=tx.payment_method or '',
            items=tx.items or [],
            amount_tax_excl=tx.amount_tax_excl,
            tax_amount=tx.tax_amount,
            tax_rate=tx.tax_rate,
            confidence=tx.confidence or 0.5,
        )
