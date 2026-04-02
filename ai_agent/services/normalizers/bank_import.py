from decimal import Decimal

from ai_agent.services.parsers.csv_parser import RawBankRow
from .base import BaseNormalizer


class BankImportNormalizer(BaseNormalizer):

    def normalize(self, user, row: RawBankRow, import_id: int) -> 'UnifiedTransaction':
        if row.amount < 0:
            direction = 'outflow'
            amount = abs(row.amount)
        else:
            direction = 'inflow'
            amount = row.amount

        return self._build(
            user=user,
            source_type='bank_import',
            source_id=f'bank_{row.date}_{row.label[:40]}_{row.amount}',
            direction=direction,
            category='other',
            amount=amount,
            currency=row.currency,
            transaction_date=row.date,
            vendor_name=row.label,
            description=row.label,
            confidence=0.90,
        )
