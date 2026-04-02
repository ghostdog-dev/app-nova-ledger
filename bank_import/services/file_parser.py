"""
Intelligent bank file parser.

Handles CSV, XLS, XLSX, OFX, QIF, and CFONB formats with auto-detection of:
- File format (by extension + content sniffing)
- Encoding (UTF-8, Latin-1, Windows-1252, etc.)
- CSV separator (; , \t |)
- Column mapping (date, amount, description, etc.)
- Date formats (DD/MM/YYYY, YYYY-MM-DD, DD-MM-YY, etc.)
- Number formats (French: 1 234,56 vs English: 1,234.56)
"""

import csv
import hashlib
import io
import logging
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

import chardet

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column name patterns — map user's column headers to our canonical fields
# ---------------------------------------------------------------------------

COLUMN_PATTERNS = {
    'date': [
        r'^date$', r'^date\s*op', r'^date\s*d[\'\u2019]?op', r'^date\s*comptable',
        r'^date\s*transaction', r'^booking\s*date', r'^transaction\s*date',
        r'^fecha', r'^datum', r'^data$',
    ],
    'value_date': [
        r'^date\s*valeur', r'^date\s*de\s*valeur', r'^value\s*date',
        r'^date\s*val', r'^fecha\s*valor',
    ],
    'amount': [
        r'^montant$', r'^amount$', r'^somme$', r'^valeur$', r'^betrag$',
        r'^montant\s*ttc', r'^montant\s*eur', r'^montant\s*\(', r'^importe$',
    ],
    'credit': [
        r'^cr[ée]dit$', r'^credit$', r'^encaissement', r'^recette',
        r'^montant\s*cr[ée]dit', r'^entrant',
    ],
    'debit': [
        r'^d[ée]bit$', r'^debit$', r'^d[ée]caissement', r'^d[ée]pense',
        r'^montant\s*d[ée]bit', r'^sortant',
    ],
    'description': [
        r'^libell[ée]', r'^description', r'^label', r'^intitul[ée]',
        r'^motif', r'^communication', r'^narrative', r'^details?$',
        r'^objet', r'^wording', r'^bezeichnung', r'^text$',
    ],
    'reference': [
        r'^r[ée]f[ée]rence', r'^reference', r'^ref$', r'^num[ée]ro',
        r'^n[°o]\s*', r'^id$', r'^transaction\s*id', r'^code$',
    ],
    'counterparty': [
        r'^tiers', r'^b[ée]n[ée]ficiaire', r'^contrepartie', r'^counterparty',
        r'^payee', r'^payer', r'^nom', r'^name$', r'^emetteur',
        r'^destinataire', r'^d[ée]biteur', r'^cr[ée]ancier',
    ],
    'category': [
        r'^cat[ée]gorie', r'^category', r'^type$', r'^nature$',
        r'^rubrique', r'^poste',
    ],
    'balance_after': [
        r'^solde', r'^balance', r'^solde\s*apr', r'^running\s*balance',
        r'^solde\s*comptable',
    ],
    'currency': [
        r'^devise', r'^currency', r'^monnaie', r'^ccy$', r'^w[äa]hrung',
    ],
    'transaction_type': [
        r'^type\s*op', r'^type\s*transaction', r'^operation\s*type',
        r'^mode\s*paiement', r'^payment\s*method', r'^moyen',
    ],
}

# Pre-compile
_COMPILED_PATTERNS = {
    field: [re.compile(p, re.IGNORECASE) for p in patterns]
    for field, patterns in COLUMN_PATTERNS.items()
}

# ---------------------------------------------------------------------------
# Date format detection
# ---------------------------------------------------------------------------

DATE_FORMATS = [
    # French formats
    ('%d/%m/%Y', r'^\d{2}/\d{2}/\d{4}$'),
    ('%d-%m-%Y', r'^\d{2}-\d{2}-\d{4}$'),
    ('%d.%m.%Y', r'^\d{2}\.\d{2}\.\d{4}$'),
    ('%d/%m/%y', r'^\d{2}/\d{2}/\d{2}$'),
    ('%d-%m-%y', r'^\d{2}-\d{2}-\d{2}$'),
    # ISO
    ('%Y-%m-%d', r'^\d{4}-\d{2}-\d{2}$'),
    ('%Y/%m/%d', r'^\d{4}/\d{2}/\d{2}$'),
    # US
    ('%m/%d/%Y', r'^\d{2}/\d{2}/\d{4}$'),
    # Compact
    ('%Y%m%d', r'^\d{8}$'),
    ('%d%m%Y', r'^\d{8}$'),
]


def _parse_date(value: str) -> date | None:
    """Try multiple date formats, prefer DD/MM/YYYY (French) over MM/DD/YYYY."""
    value = value.strip()
    if not value:
        return None

    # Try ISO first (unambiguous)
    for fmt in ['%Y-%m-%d', '%Y/%m/%d']:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue

    # Try French formats (DD/MM/YYYY) — prioritized
    for fmt in ['%d/%m/%Y', '%d-%m-%Y', '%d.%m.%Y', '%d/%m/%y', '%d-%m-%y']:
        try:
            d = datetime.strptime(value, fmt).date()
            # Sanity check: day <= 31, month <= 12
            if d.month <= 12 and d.day <= 31:
                return d
        except ValueError:
            continue

    # Compact 8-digit
    if re.match(r'^\d{8}$', value):
        for fmt in ['%Y%m%d', '%d%m%Y']:
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue

    return None


# ---------------------------------------------------------------------------
# Amount parsing
# ---------------------------------------------------------------------------

def _parse_amount(value: str) -> Decimal | None:
    """Parse amount from various French and international formats.

    Handles:
      - French: "1 234,56" or "1.234,56" or "-1234,56"
      - English: "1,234.56" or "1234.56"
      - Parentheses for negative: "(1234.56)"
      - Currency symbols: "€", "$", "EUR"
      - Spaces as thousands separator
    """
    if not value or not isinstance(value, str):
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        return None

    value = value.strip()
    if not value or value == '-':
        return None

    # Remove currency symbols and whitespace
    value = re.sub(r'[€$£\s\u00a0\u202f]', '', value)
    value = re.sub(r'(EUR|USD|GBP|CHF)', '', value, flags=re.IGNORECASE).strip()

    # Handle parentheses = negative
    if value.startswith('(') and value.endswith(')'):
        value = '-' + value[1:-1]

    # Detect French vs English number format
    # French: comma is decimal, dot/space is thousands (1.234,56 or 1 234,56)
    # English: dot is decimal, comma is thousands (1,234.56)
    has_comma = ',' in value
    has_dot = '.' in value

    if has_comma and has_dot:
        # Both present — which comes last is the decimal separator
        last_comma = value.rfind(',')
        last_dot = value.rfind('.')
        if last_comma > last_dot:
            # French: 1.234,56 → remove dots, replace comma with dot
            value = value.replace('.', '').replace(',', '.')
        else:
            # English: 1,234.56 → remove commas
            value = value.replace(',', '')
    elif has_comma and not has_dot:
        # Could be French decimal (1234,56) or thousands (1,234)
        # If comma is followed by exactly 2 digits at the end → decimal
        if re.search(r',\d{1,2}$', value):
            value = value.replace(',', '.')
        elif re.search(r',\d{3}', value):
            # Thousands separator (no decimal)
            value = value.replace(',', '')
        else:
            # Default: treat comma as decimal
            value = value.replace(',', '.')
    # If only dot: keep as-is (English decimal or thousands)
    # If dot is followed by exactly 3 digits and nothing after → thousands
    elif has_dot and not has_comma:
        if re.search(r'\.\d{3}$', value) and re.search(r'\d{1,3}\.\d{3}$', value):
            # Ambiguous: could be 1.234 (French thousands) or 1.234 (decimal)
            # If multiple dots → thousands separator
            if value.count('.') > 1:
                value = value.replace('.', '')
            # else keep as-is (assume decimal)

    # Remove any remaining non-numeric chars except - and .
    value = re.sub(r'[^\d.\-+]', '', value)

    try:
        return Decimal(value)
    except (InvalidOperation, ValueError):
        return None


# ---------------------------------------------------------------------------
# CSV parsing
# ---------------------------------------------------------------------------

def _detect_encoding(raw_bytes: bytes) -> str:
    """Detect file encoding using chardet."""
    result = chardet.detect(raw_bytes[:10000])
    encoding = result.get('encoding', 'utf-8') or 'utf-8'
    # Normalize common aliases
    encoding = encoding.lower().replace('-', '_')
    if encoding in ('ascii', 'iso_8859_1', 'iso8859_1', 'latin_1', 'latin1'):
        encoding = 'latin-1'
    if encoding in ('windows_1252', 'cp1252'):
        encoding = 'cp1252'
    return encoding


def _detect_separator(text: str) -> str:
    """Detect CSV separator by counting occurrences in first few lines."""
    lines = text.split('\n')[:10]
    candidates = {';': 0, ',': 0, '\t': 0, '|': 0}
    for line in lines:
        for sep in candidates:
            candidates[sep] += line.count(sep)
    # Return the most frequent one (semicolons very common in French CSVs)
    best = max(candidates, key=candidates.get)
    if candidates[best] == 0:
        return ','
    return best


def _detect_column_mapping(headers: list[str]) -> dict[str, str]:
    """Map file column headers to our canonical field names."""
    mapping = {}
    for header in headers:
        clean = header.strip().lower()
        if not clean:
            continue
        for field, patterns in _COMPILED_PATTERNS.items():
            for pattern in patterns:
                if pattern.search(clean):
                    if field not in mapping:
                        mapping[field] = header
                    break
    return mapping


def _has_separate_debit_credit(mapping: dict) -> bool:
    """Check if the file uses separate debit/credit columns instead of a single amount."""
    return 'debit' in mapping or 'credit' in mapping


def _compute_amount_from_row(row: dict, mapping: dict) -> Decimal | None:
    """Compute the transaction amount from the row, handling single amount or debit/credit columns."""
    if 'amount' in mapping:
        return _parse_amount(row.get(mapping['amount'], ''))

    # Separate debit/credit columns
    credit = _parse_amount(row.get(mapping.get('credit', ''), '')) or Decimal('0')
    debit = _parse_amount(row.get(mapping.get('debit', ''), '')) or Decimal('0')

    if credit and not debit:
        return credit
    if debit and not credit:
        return -abs(debit)
    if credit and debit:
        return credit - debit

    return None


def parse_csv(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse a CSV file with auto-detection of encoding, separator, columns."""
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors='replace')

    # Strip BOM
    text = text.lstrip('\ufeff')

    # Skip common header lines from bank exports (lines starting with special chars)
    lines = text.split('\n')
    skip_count = 0
    for line in lines:
        stripped = line.strip()
        if not stripped:
            skip_count += 1
            continue
        # Skip lines that look like metadata (no separator, or start with #, or contain "Date de" etc.)
        if stripped.startswith('#') or stripped.startswith('//'):
            skip_count += 1
            continue
        break

    text = '\n'.join(lines[skip_count:])
    separator = _detect_separator(text)

    reader = csv.DictReader(io.StringIO(text), delimiter=separator)
    headers = reader.fieldnames or []

    if not headers:
        raise ValueError('No headers found in CSV file')

    mapping = _detect_column_mapping(headers)

    if 'date' not in mapping:
        # Fallback: try first column as date if it contains date-like values
        if headers:
            mapping['date'] = headers[0]

    if 'amount' not in mapping and 'debit' not in mapping and 'credit' not in mapping:
        # Try to find numeric columns
        for h in headers:
            if h not in mapping.values():
                mapping['amount'] = h
                break

    if 'description' not in mapping:
        # Use the longest text column that's not already mapped
        for h in headers:
            if h not in mapping.values():
                mapping['description'] = h
                break

    rows = list(reader)
    transactions = []

    for row in rows:
        date_val = _parse_date(row.get(mapping.get('date', ''), ''))
        amount_val = _compute_amount_from_row(row, mapping)

        if date_val is None or amount_val is None:
            continue

        txn = {
            'date': date_val,
            'amount': amount_val,
            'description': row.get(mapping.get('description', ''), '').strip(),
            'value_date': _parse_date(row.get(mapping.get('value_date', ''), '')),
            'reference': row.get(mapping.get('reference', ''), '').strip(),
            'counterparty': row.get(mapping.get('counterparty', ''), '').strip(),
            'category': row.get(mapping.get('category', ''), '').strip(),
            'balance_after': _parse_amount(row.get(mapping.get('balance_after', ''), '')),
            'currency': row.get(mapping.get('currency', ''), '').strip().upper() or 'EUR',
            'transaction_type': row.get(mapping.get('transaction_type', ''), '').strip(),
            'raw_data': {k: v for k, v in row.items() if v},
        }
        transactions.append(txn)

    return {
        'format': 'csv',
        'encoding': encoding,
        'separator': separator,
        'headers': headers,
        'column_mapping': mapping,
        'transactions': transactions,
        'preview': rows[:5],
    }


# ---------------------------------------------------------------------------
# Excel parsing (XLSX / XLS)
# ---------------------------------------------------------------------------

def parse_xlsx(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse an XLSX file."""
    import openpyxl

    wb = openpyxl.load_workbook(io.BytesIO(raw_bytes), read_only=True, data_only=True)
    ws = wb.active

    rows_iter = ws.iter_rows(values_only=True)

    # Find header row (first row with 3+ non-empty cells)
    headers = []
    data_rows = []
    header_found = False

    for row in rows_iter:
        cells = [str(c).strip() if c is not None else '' for c in row]
        non_empty = sum(1 for c in cells if c)
        if not header_found and non_empty >= 3:
            headers = cells
            header_found = True
            continue
        if header_found:
            if any(c for c in cells):
                data_rows.append(dict(zip(headers, cells)))

    wb.close()

    if not headers:
        raise ValueError('No headers found in Excel file')

    mapping = _detect_column_mapping(headers)
    return _build_result_from_rows(data_rows, headers, mapping, 'xlsx')


def parse_xls(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse a legacy XLS file."""
    import xlrd

    wb = xlrd.open_workbook(file_contents=raw_bytes)
    ws = wb.sheet_by_index(0)

    headers = []
    data_rows = []
    header_found = False

    for row_idx in range(ws.nrows):
        cells = [str(ws.cell_value(row_idx, col_idx)).strip() for col_idx in range(ws.ncols)]
        non_empty = sum(1 for c in cells if c)
        if not header_found and non_empty >= 3:
            headers = cells
            header_found = True
            continue
        if header_found and any(c for c in cells):
            data_rows.append(dict(zip(headers, cells)))

    if not headers:
        raise ValueError('No headers found in XLS file')

    mapping = _detect_column_mapping(headers)
    return _build_result_from_rows(data_rows, headers, mapping, 'xls')


def _build_result_from_rows(rows: list[dict], headers: list[str], mapping: dict, fmt: str) -> dict:
    """Shared builder for Excel formats."""
    if 'date' not in mapping and headers:
        mapping['date'] = headers[0]
    if 'amount' not in mapping and 'debit' not in mapping and 'credit' not in mapping:
        for h in headers:
            if h not in mapping.values():
                mapping['amount'] = h
                break
    if 'description' not in mapping:
        for h in headers:
            if h not in mapping.values():
                mapping['description'] = h
                break

    transactions = []
    for row in rows:
        date_val = _parse_date(row.get(mapping.get('date', ''), ''))
        amount_val = _compute_amount_from_row(row, mapping)
        if date_val is None or amount_val is None:
            continue
        txn = {
            'date': date_val,
            'amount': amount_val,
            'description': row.get(mapping.get('description', ''), '').strip(),
            'value_date': _parse_date(row.get(mapping.get('value_date', ''), '')),
            'reference': row.get(mapping.get('reference', ''), '').strip(),
            'counterparty': row.get(mapping.get('counterparty', ''), '').strip(),
            'category': row.get(mapping.get('category', ''), '').strip(),
            'balance_after': _parse_amount(row.get(mapping.get('balance_after', ''), '')),
            'currency': row.get(mapping.get('currency', ''), '').strip().upper() or 'EUR',
            'transaction_type': row.get(mapping.get('transaction_type', ''), '').strip(),
            'raw_data': {k: v for k, v in row.items() if v},
        }
        transactions.append(txn)

    return {
        'format': fmt,
        'encoding': 'binary',
        'separator': '',
        'headers': headers,
        'column_mapping': mapping,
        'transactions': transactions,
        'preview': rows[:5],
    }


# ---------------------------------------------------------------------------
# OFX parsing
# ---------------------------------------------------------------------------

def parse_ofx(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse an OFX/QFX file (Open Financial Exchange)."""
    from ofxparse import OfxParser

    ofx = OfxParser.parse(io.BytesIO(raw_bytes))
    transactions = []
    account_id = ''
    bank_name = ''

    for account in ofx.accounts:
        account_id = account.account_id or ''
        if hasattr(account, 'institution') and account.institution:
            bank_name = getattr(account.institution, 'organization', '')

        for txn in account.statement.transactions:
            amount = Decimal(str(txn.amount))
            transactions.append({
                'date': txn.date.date() if hasattr(txn.date, 'date') else txn.date,
                'amount': amount,
                'description': (txn.memo or txn.payee or '').strip(),
                'value_date': None,
                'reference': txn.id or '',
                'counterparty': (txn.payee or '').strip(),
                'category': (txn.type or '').strip(),
                'balance_after': None,
                'currency': account.statement.currency or 'EUR',
                'transaction_type': txn.type or '',
                'raw_data': {
                    'id': txn.id,
                    'type': txn.type,
                    'memo': txn.memo,
                    'payee': txn.payee,
                    'amount': str(txn.amount),
                    'checknum': getattr(txn, 'checknum', ''),
                },
            })

    return {
        'format': 'ofx',
        'encoding': 'binary',
        'separator': '',
        'headers': [],
        'column_mapping': {'auto': 'OFX standard'},
        'transactions': transactions,
        'preview': [],
        'bank_name': bank_name,
        'account_id': account_id,
    }


# ---------------------------------------------------------------------------
# QIF parsing
# ---------------------------------------------------------------------------

def parse_qif(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse a QIF file (Quicken Interchange Format)."""
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors='replace')

    transactions = []
    current = {}

    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue

        if line.startswith('^'):
            # End of transaction
            if 'date' in current and 'amount' in current:
                transactions.append(current)
            current = {}
        elif line.startswith('D'):
            current['date'] = _parse_date(line[1:])
        elif line.startswith('T') or line.startswith('U'):
            current['amount'] = _parse_amount(line[1:])
        elif line.startswith('P'):
            current['counterparty'] = line[1:].strip()
            current['description'] = current.get('description', '') or line[1:].strip()
        elif line.startswith('M'):
            current['description'] = line[1:].strip()
        elif line.startswith('N'):
            current['reference'] = line[1:].strip()
        elif line.startswith('L'):
            current['category'] = line[1:].strip()

    # Don't forget last transaction
    if 'date' in current and 'amount' in current:
        transactions.append(current)

    # Normalize
    for txn in transactions:
        txn.setdefault('description', '')
        txn.setdefault('value_date', None)
        txn.setdefault('reference', '')
        txn.setdefault('counterparty', '')
        txn.setdefault('category', '')
        txn.setdefault('balance_after', None)
        txn.setdefault('currency', 'EUR')
        txn.setdefault('transaction_type', '')
        txn['raw_data'] = {k: str(v) for k, v in txn.items() if k != 'raw_data'}

    return {
        'format': 'qif',
        'encoding': encoding,
        'separator': '',
        'headers': [],
        'column_mapping': {'auto': 'QIF standard'},
        'transactions': transactions,
        'preview': [],
    }


# ---------------------------------------------------------------------------
# CFONB parsing (French banking format — fixed-width)
# ---------------------------------------------------------------------------

def parse_cfonb(raw_bytes: bytes, filename: str = '') -> dict:
    """Parse a CFONB 120 file (French standard fixed-width bank statement)."""
    encoding = _detect_encoding(raw_bytes)
    text = raw_bytes.decode(encoding, errors='replace')

    transactions = []
    current_txn = None

    for line in text.split('\n'):
        if len(line) < 120:
            continue

        record_type = line[0:2]

        if record_type == '04':
            # Transaction record
            date_str = line[34:40]  # DDMMYY
            try:
                txn_date = datetime.strptime(date_str, '%d%m%y').date()
            except ValueError:
                continue

            amount_str = line[90:103].strip()
            sign = line[103:104]  # C=credit, D=debit, blank

            try:
                amount = Decimal(amount_str) / Decimal('100')
            except (InvalidOperation, ValueError):
                continue

            if sign == 'D' or sign == '{':
                amount = -amount

            description = line[48:79].strip()
            reference = line[81:88].strip()
            txn_type = line[40:42].strip()

            current_txn = {
                'date': txn_date,
                'amount': amount,
                'description': description,
                'value_date': None,
                'reference': reference,
                'counterparty': '',
                'category': '',
                'balance_after': None,
                'currency': 'EUR',
                'transaction_type': txn_type,
                'raw_data': {'raw_line': line.rstrip()},
            }
            transactions.append(current_txn)

        elif record_type == '05' and current_txn:
            # Complementary info for previous transaction
            extra = line[48:118].strip()
            if extra:
                current_txn['description'] += ' ' + extra
                current_txn['description'] = current_txn['description'].strip()

    return {
        'format': 'cfonb',
        'encoding': encoding,
        'separator': '',
        'headers': [],
        'column_mapping': {'auto': 'CFONB 120 standard'},
        'transactions': transactions,
        'preview': [],
    }


# ---------------------------------------------------------------------------
# Main dispatcher
# ---------------------------------------------------------------------------

PARSERS = {
    '.csv': parse_csv,
    '.txt': parse_csv,  # many banks export CSV with .txt extension
    '.tsv': parse_csv,
    '.xlsx': parse_xlsx,
    '.xls': parse_xls,
    '.ofx': parse_ofx,
    '.qfx': parse_ofx,  # QFX is just OFX from Quicken
    '.qif': parse_qif,
    '.cfonb': parse_cfonb,
}


def parse_bank_file(raw_bytes: bytes, filename: str) -> dict:
    """Auto-detect format and parse a bank file.

    Returns a dict with:
      - format: str
      - encoding: str
      - separator: str (CSV only)
      - headers: list[str]
      - column_mapping: dict
      - transactions: list[dict] — each has: date, amount, description, ...
      - preview: list[dict] — first 5 raw rows
    """
    ext = Path(filename).suffix.lower()

    # Try by extension first
    parser = PARSERS.get(ext)

    if parser is None:
        # Content-based detection
        if raw_bytes[:9] == b'OFXHEADER' or b'<OFX>' in raw_bytes[:500]:
            parser = parse_ofx
        elif raw_bytes[:1] == b'!' or b'\n^' in raw_bytes[:500]:
            parser = parse_qif
        elif len(raw_bytes.split(b'\n')[0]) >= 120:
            # Fixed-width lines ≥ 120 chars → likely CFONB
            parser = parse_cfonb
        else:
            # Default to CSV
            parser = parse_csv

    result = parser(raw_bytes, filename)

    if not result.get('transactions'):
        raise ValueError(f'No transactions found in {filename}. Check the file format and content.')

    logger.info(
        'Parsed %s: format=%s, encoding=%s, %d transactions',
        filename, result['format'], result.get('encoding', '?'), len(result['transactions']),
    )
    return result


def compute_fingerprint(user_id: int, txn: dict) -> str:
    """Compute a unique fingerprint for deduplication.

    Combines date + amount + description to detect duplicates across imports.
    """
    raw = f"{user_id}|{txn['date']}|{txn['amount']}|{txn.get('description', '')}|{txn.get('reference', '')}"
    return hashlib.sha256(raw.encode()).hexdigest()
