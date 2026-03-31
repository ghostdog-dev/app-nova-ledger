"""
CSV Bank Statement Parser — multi-bank support.

Strategy:
1. Detect encoding + separator
2. Match known bank signatures (headers)
3. Heuristic column mapping for unknown banks
4. LLM fallback (not implemented here — handled by orchestrator)
"""
import csv
import io
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


@dataclass
class RawBankRow:
    date: date
    label: str
    amount: Decimal
    currency: str = 'EUR'
    value_date: date | None = None
    reference: str = ''
    raw_data: dict = field(default_factory=dict)


@dataclass
class ParseResult:
    transactions: list[RawBankRow]
    bank_name: str | None = None
    account_id: str | None = None
    date_range: tuple[date, date] | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ColumnMapping:
    date_col: int | None = None
    value_date_col: int | None = None
    label_col: int | None = None
    amount_col: int | None = None
    debit_col: int | None = None
    credit_col: int | None = None
    currency_col: int | None = None
    reference_col: int | None = None
    date_format: str = '%d/%m/%Y'
    confidence: float = 0.0

    def compute_confidence(self) -> float:
        score = 0.0
        if self.date_col is not None:
            score += 0.3
        if self.amount_col is not None or (self.debit_col is not None and self.credit_col is not None):
            score += 0.4
        if self.label_col is not None:
            score += 0.3
        self.confidence = score
        return score


# Known bank CSV signatures
KNOWN_SIGNATURES = {
    'bnp': {
        'headers_match': lambda h: any('opération' in x or 'operation' in x for x in h) and any('libellé' in x or 'libelle' in x for x in h),
        'date_format': '%d/%m/%Y',
        'encoding': 'latin-1',
        'separator': ';',
        'build_mapping': lambda h: _build_bnp_mapping(h),
    },
    'revolut': {
        'headers_match': lambda h: 'started date' in h and 'description' in h and 'amount' in h,
        'date_format': '%Y-%m-%d %H:%M:%S',
        'encoding': 'utf-8',
        'separator': ',',
        'build_mapping': lambda h: _build_revolut_mapping(h),
    },
    'n26': {
        'headers_match': lambda h: 'payee' in h and 'transaction type' in h,
        'date_format': '%Y-%m-%d',
        'encoding': 'utf-8',
        'separator': ',',
        'build_mapping': lambda h: _build_n26_mapping(h),
    },
}


def _build_bnp_mapping(headers):
    m = ColumnMapping(date_format='%d/%m/%Y')
    for i, h in enumerate(headers):
        if 'opération' in h or 'operation' in h:
            m.date_col = i
        elif 'libellé' in h or 'libelle' in h:
            m.label_col = i
        elif 'débit' in h or 'debit' in h:
            m.debit_col = i
        elif 'crédit' in h or 'credit' in h:
            m.credit_col = i
        elif 'montant' in h:
            m.amount_col = i
    m.compute_confidence()
    return m


def _build_revolut_mapping(headers):
    m = ColumnMapping(date_format='%Y-%m-%d %H:%M:%S')
    for i, h in enumerate(headers):
        if h == 'started date':
            m.date_col = i
        elif h == 'completed date':
            m.value_date_col = i
        elif h == 'description':
            m.label_col = i
        elif h == 'amount':
            m.amount_col = i
        elif h == 'currency':
            m.currency_col = i
    m.compute_confidence()
    return m


def _build_n26_mapping(headers):
    m = ColumnMapping(date_format='%Y-%m-%d')
    for i, h in enumerate(headers):
        if h == 'date':
            m.date_col = i
        elif h == 'payee':
            m.label_col = i
        elif 'amount' in h:
            m.amount_col = i
    m.compute_confidence()
    return m


# Heuristic column detection patterns
_DATE_PATTERNS = ['date', 'datum', 'fecha', 'data', 'booking', 'opération', 'operation']
_AMOUNT_PATTERNS = ['amount', 'montant', 'betrag', 'importe', 'somme', 'total']
_DEBIT_PATTERNS = ['débit', 'debit', 'soll', 'charge', 'sortie']
_CREDIT_PATTERNS = ['crédit', 'credit', 'haben', 'deposit', 'entrée', 'entree']
_LABEL_PATTERNS = ['libellé', 'libelle', 'label', 'description', 'wording', 'payee',
                   'beneficiary', 'text', 'verwendungszweck', 'concepto', 'communication']
_CURRENCY_PATTERNS = ['currency', 'devise', 'währung', 'divisa', 'monnaie']
_DATE_FORMATS = ['%d/%m/%Y', '%Y-%m-%d', '%d-%m-%Y', '%d.%m.%Y', '%m/%d/%Y',
                 '%Y-%m-%d %H:%M:%S', '%d/%m/%Y %H:%M']


class CSVBankParser:

    def parse(self, file_content: bytes, filename: str | None = None) -> ParseResult | None:
        if not file_content or not file_content.strip():
            return None

        encoding = self._detect_encoding(file_content)
        text = file_content.decode(encoding, errors='replace')

        separator = self._detect_separator(text)
        headers = self._read_headers(text, separator)

        if not headers:
            return None

        normalized_headers = [h.lower().strip() for h in headers]

        # Try known bank signatures
        for bank_name, sig in KNOWN_SIGNATURES.items():
            if sig['headers_match'](normalized_headers):
                mapping = sig['build_mapping'](normalized_headers)
                return self._parse_with_mapping(
                    text, mapping, separator, bank_name=bank_name,
                )

        # Heuristic mapping
        mapping = self._infer_column_mapping(normalized_headers)
        if mapping.confidence >= 0.7:
            return self._parse_with_mapping(text, mapping, separator)

        # Try with different date formats
        for fmt in _DATE_FORMATS:
            mapping.date_format = fmt
            result = self._parse_with_mapping(text, mapping, separator)
            if result and result.transactions:
                return result

        return None

    def _detect_encoding(self, content: bytes) -> str:
        try:
            import chardet
            result = chardet.detect(content[:10000])
            if result and result.get('encoding'):
                return result['encoding']
        except ImportError:
            pass

        # Fallback: try utf-8, then latin-1
        try:
            content.decode('utf-8')
            return 'utf-8'
        except UnicodeDecodeError:
            return 'latin-1'

    def _detect_separator(self, text: str) -> str:
        first_line = text.split('\n')[0] if text else ''
        semicolons = first_line.count(';')
        commas = first_line.count(',')
        tabs = first_line.count('\t')

        if semicolons > commas and semicolons > tabs:
            return ';'
        if tabs > commas:
            return '\t'
        return ','

    def _read_headers(self, text: str, separator: str) -> list[str]:
        reader = csv.reader(io.StringIO(text), delimiter=separator)
        try:
            headers = next(reader)
            return [h.strip().strip('"') for h in headers]
        except StopIteration:
            return []

    def _infer_column_mapping(self, headers: list[str]) -> ColumnMapping:
        mapping = ColumnMapping()

        for i, h in enumerate(headers):
            if any(p in h for p in _DEBIT_PATTERNS) and mapping.debit_col is None:
                mapping.debit_col = i
            elif any(p in h for p in _CREDIT_PATTERNS) and mapping.credit_col is None:
                mapping.credit_col = i
            elif any(p in h for p in _AMOUNT_PATTERNS) and mapping.amount_col is None:
                mapping.amount_col = i
            elif any(p in h for p in _LABEL_PATTERNS) and mapping.label_col is None:
                mapping.label_col = i
            elif any(p in h for p in _CURRENCY_PATTERNS) and mapping.currency_col is None:
                mapping.currency_col = i
            elif any(p in h for p in _DATE_PATTERNS):
                if mapping.date_col is None:
                    mapping.date_col = i
                elif 'valeur' in h or 'value' in h:
                    mapping.value_date_col = i

        mapping.compute_confidence()
        return mapping

    def _parse_with_mapping(self, text: str, mapping: ColumnMapping,
                            separator: str, bank_name: str | None = None) -> ParseResult:
        reader = csv.reader(io.StringIO(text), delimiter=separator)
        next(reader, None)  # skip header

        transactions = []
        warnings = []
        dates = []

        for row_num, row in enumerate(reader, start=2):
            if not row or all(not cell.strip() for cell in row):
                continue

            try:
                # Parse date
                tx_date = self._parse_date(
                    self._get_cell(row, mapping.date_col), mapping.date_format
                )
                if not tx_date:
                    warnings.append(f'Row {row_num}: could not parse date')
                    continue

                # Parse amount
                amount = self._parse_amount(row, mapping)
                if amount is None:
                    warnings.append(f'Row {row_num}: could not parse amount')
                    continue

                # Parse label
                label = self._get_cell(row, mapping.label_col) or f'Row {row_num}'

                # Parse currency
                currency = self._get_cell(row, mapping.currency_col) or 'EUR'

                # Parse value date
                value_date = self._parse_date(
                    self._get_cell(row, mapping.value_date_col), mapping.date_format
                )

                raw = {str(i): cell for i, cell in enumerate(row)}

                transactions.append(RawBankRow(
                    date=tx_date,
                    label=label.strip(),
                    amount=amount,
                    currency=currency.upper(),
                    value_date=value_date,
                    raw_data=raw,
                ))
                dates.append(tx_date)

            except Exception as e:
                warnings.append(f'Row {row_num}: {e}')

        date_range = (min(dates), max(dates)) if dates else None

        return ParseResult(
            transactions=transactions,
            bank_name=bank_name,
            date_range=date_range,
            warnings=warnings,
        )

    def _get_cell(self, row: list, col: int | None) -> str:
        if col is None or col >= len(row):
            return ''
        return row[col].strip().strip('"')

    def _parse_date(self, value: str, fmt: str) -> date | None:
        if not value:
            return None
        value = value.strip().strip('"')
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            # Try common fallbacks
            for fallback_fmt in _DATE_FORMATS:
                try:
                    return datetime.strptime(value, fallback_fmt).date()
                except ValueError:
                    continue
        return None

    def _parse_amount(self, row: list, mapping: ColumnMapping) -> Decimal | None:
        if mapping.amount_col is not None:
            raw = self._get_cell(row, mapping.amount_col)
            return self._clean_decimal(raw)

        if mapping.debit_col is not None or mapping.credit_col is not None:
            debit_raw = self._get_cell(row, mapping.debit_col)
            credit_raw = self._get_cell(row, mapping.credit_col)

            debit = self._clean_decimal(debit_raw)
            credit = self._clean_decimal(credit_raw)

            if debit and debit != Decimal('0'):
                return -abs(debit)
            if credit and credit != Decimal('0'):
                return abs(credit)
            if debit == Decimal('0') and credit == Decimal('0'):
                return Decimal('0')

        return None

    def _clean_decimal(self, raw: str) -> Decimal | None:
        if not raw:
            return None
        # Remove currency symbols, spaces, and normalize decimal separators
        cleaned = raw.strip().replace(' ', '').replace('\u00a0', '')
        cleaned = re.sub(r'[€$£]', '', cleaned)
        cleaned = cleaned.replace('+', '')

        # Handle French decimal format: 1.234,56 → 1234.56
        if ',' in cleaned and '.' in cleaned:
            if cleaned.index('.') < cleaned.index(','):
                cleaned = cleaned.replace('.', '').replace(',', '.')
            else:
                cleaned = cleaned.replace(',', '')
        elif ',' in cleaned:
            cleaned = cleaned.replace(',', '.')

        try:
            return Decimal(cleaned)
        except (InvalidOperation, ValueError):
            return None
