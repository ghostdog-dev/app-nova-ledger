"""Shared utilities for banking services."""
import re


def normalize_vendor(name):
    """Normalize vendor name for comparison. Lowercase, strip suffixes, common bank prefixes."""
    if not name:
        return ''
    name = name.lower().strip()
    # Strip common bank label prefixes
    for prefix in ['cb*', 'cb ', 'carte ', 'paiement par carte ', 'prlv ', 'vir ', 'virement ']:
        if name.startswith(prefix):
            name = name[len(prefix):]
    # Strip corporate suffixes
    name = re.sub(r'\b(inc\.?|ltd\.?|llc\.?|pbc\.?|sas\.?|sa\.?|gmbh\.?|co\.?|corp\.?|limited|pty\.?)\s*$', '', name)
    # Strip city names at end (common pattern: "VENDOR PARIS", "VENDOR LYON 02")
    name = re.sub(r'\s+(paris|lyon|marseille|bordeaux|toulouse|nantes|lille|nice|strasbourg|montpellier)\s*\d*\s*$', '', name)
    # Strip trailing numbers/codes
    name = re.sub(r'\s+\d{2,}$', '', name)
    # Clean up
    name = name.strip(' ,.*')
    name = re.sub(r'\s+', ' ', name).strip()
    return name
