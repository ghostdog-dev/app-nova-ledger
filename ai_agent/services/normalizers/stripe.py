from datetime import date as date_type
from decimal import Decimal

from .base import BaseNormalizer


class StripeNormalizer(BaseNormalizer):

    def normalize_charge(self, user, charge) -> 'UnifiedTransaction':
        amount_decimal = Decimal(str(charge.amount)) / Decimal('100')
        tx_date = self._parse_date(charge.created_at_stripe)
        vendor = charge.statement_descriptor or charge.description or ''

        return self._build(
            user=user,
            source_type='stripe',
            source_id=charge.stripe_id,
            direction='inflow',
            category='revenue',
            amount=amount_decimal,
            currency=(charge.currency or 'eur').upper(),
            transaction_date=tx_date,
            vendor_name=vendor,
            description=charge.description or '',
            payment_method=getattr(charge, 'payment_method_type', '') or '',
            confidence=0.95,
        )

    def normalize_payout(self, user, payout) -> 'UnifiedTransaction':
        amount_decimal = Decimal(str(payout.amount)) / Decimal('100')
        tx_date = self._parse_date(payout.arrival_date)

        return self._build(
            user=user,
            source_type='stripe',
            source_id=payout.stripe_id,
            direction='outflow',
            category='transfer',
            amount=amount_decimal,
            currency=(payout.currency or 'eur').upper(),
            transaction_date=tx_date,
            vendor_name='Stripe Payout',
            description=f'Payout {payout.stripe_id}',
            confidence=0.99,
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
