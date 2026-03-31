from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class MollieNormalizer(BaseNormalizer):

    def normalize_payment(self, user, payment) -> 'UnifiedTransaction':
        amount = payment.amount if isinstance(payment.amount, Decimal) else Decimal(str(payment.amount))
        tx_date = self._parse_date(payment.paid_at) or self._parse_date(payment.created_at_mollie)

        return self._build(
            user=user,
            source_type='mollie',
            source_id=payment.mollie_id,
            direction='inflow',
            category='revenue',
            amount=amount,
            currency=(payment.currency or 'EUR').upper(),
            transaction_date=tx_date,
            vendor_name=payment.description or '',
            description=payment.description or '',
            payment_method=payment.method or '',
            confidence=0.95,
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
