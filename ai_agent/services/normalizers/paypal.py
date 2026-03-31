from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class PayPalNormalizer(BaseNormalizer):

    def normalize_transaction(self, user, tx) -> 'UnifiedTransaction':
        amount = tx.amount if isinstance(tx.amount, Decimal) else Decimal(str(tx.amount))
        tx_date = self._parse_date(tx.initiation_date)

        # PayPal: positive = received, negative = sent
        if amount >= 0:
            direction = 'inflow'
            category = 'revenue'
        else:
            direction = 'outflow'
            category = 'other'
            amount = abs(amount)

        return self._build(
            user=user,
            source_type='paypal',
            source_id=tx.paypal_id,
            direction=direction,
            category=category,
            amount=amount,
            currency=(tx.currency or 'USD').upper(),
            transaction_date=tx_date,
            vendor_name=tx.description or '',
            description=tx.description or '',
            confidence=0.90,
        )

    def _parse_date(self, value) -> date_type | None:
        if not value:
            return None
        if isinstance(value, date_type):
            return value
        s = str(value)[:10]
        try:
            return date_type.fromisoformat(s)
        except (ValueError, TypeError):
            return None
