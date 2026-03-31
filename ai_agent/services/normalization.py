"""
Unified vendor name normalization — single source of truth.

Replaces:
- banking.services.utils.normalize_vendor()
- ai_agent.services.agent._normalize_vendor_name()
- emails.services.merge._normalize_vendor()
"""
import re

# Bank transaction prefixes (FR banking conventions)
_BANK_PREFIXES = re.compile(
    r'^(CB\*?|CARTE\s+|PRLV\s+(SEPA\s+)?|VIR\s+(INST\s+|SEPA\s+)?|'
    r'CHQ\s+|RET\s+DAB\s+|ECH\s+|COTIS\s+)',
    re.IGNORECASE,
)

# Corporate suffixes
_CORPORATE_SUFFIXES = re.compile(
    r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sarl\.?|sa\.?|gmbh\.?|'
    r'co\.?|corp\.?|limited|pty\.?|plc\.?|ag\.?|bv\.?|nv\.?)\s*$',
    re.IGNORECASE,
)

# French city names commonly appended by banks
_FRENCH_CITIES = re.compile(
    r'\b(paris|lyon|marseille|toulouse|nice|nantes|strasbourg|montpellier|'
    r'bordeaux|lille|rennes|reims|toulon|grenoble|dijon|angers|'
    r'villeurbanne|roubaix|tourcoing)\b',
    re.IGNORECASE,
)

# Trailing numbers (postal codes, branch codes)
_TRAILING_NUMBERS = re.compile(r'\s+\d{2,5}\s*$')

# Multiple whitespace
_MULTI_SPACE = re.compile(r'\s+')


def normalize_vendor(name: str | None) -> str:
    if not name:
        return ''
    result = name.strip()
    result = _BANK_PREFIXES.sub('', result)
    result = result.lower()
    for _ in range(2):
        result = _CORPORATE_SUFFIXES.sub('', result).strip(' ,.')
    result = _FRENCH_CITIES.sub('', result)
    result = _TRAILING_NUMBERS.sub('', result)
    result = _MULTI_SPACE.sub(' ', result).strip()
    return result


def vendors_match(name_a: str, name_b: str) -> bool:
    if not name_a or not name_b:
        return False
    a = normalize_vendor(name_a)
    b = normalize_vendor(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    tokens_a = set(a.split())
    tokens_b = set(b.split())
    if not tokens_a or not tokens_b:
        return False
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    jaccard = len(intersection) / len(union)
    return jaccard >= 0.5
