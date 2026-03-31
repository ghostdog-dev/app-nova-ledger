from decimal import Decimal

from .base import BaseNormalizer


class BankAPINormalizer(BaseNormalizer):

    def normalize(self, user, bt) -> 'UnifiedTransaction':
        value = bt.value if isinstance(bt.value, Decimal) else Decimal(str(bt.value))

        if value < 0:
            direction = 'outflow'
            amount = abs(value)
        else:
            direction = 'inflow'
            amount = value

        # Prefer rdate (card swipe date) over date (booking date)
        tx_date = bt.rdate or bt.date

        currency = (bt.original_currency or '').upper()
        if not currency and bt.account:
            currency = getattr(bt.account, 'currency', 'EUR') or 'EUR'
        currency = currency.upper() if currency else 'EUR'

        return self._build(
            user=user,
            source_type='bank_api',
            source_id=str(bt.powens_transaction_id),
            direction=direction,
            category='other',  # enrichment agent will classify later
            amount=amount,
            currency=currency,
            transaction_date=tx_date,
            vendor_name=bt.original_wording or bt.simplified_wording or '',
            description=bt.simplified_wording or bt.original_wording or '',
            payment_method=bt.transaction_type or '',
            confidence=0.99,  # bank data is authoritative
        )
