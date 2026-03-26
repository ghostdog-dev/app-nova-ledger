"""Vendor classification rules for bank transaction enrichment."""
import re

VENDOR_RULES = [
    # SaaS / Digital services
    {"pattern": r"GOOGLE\s*\*|GOOGLE\s+CLOUD|GCP", "category_pcg": "615", "category_label": "Services numeriques", "business_personal": "business", "tva_deductible": True, "vendor_type": "saas"},
    {"pattern": r"AMAZON\s*WEB|AWS|HEROKU|OVH|DIGITAL\s*OCEAN|NETLIFY|VERCEL", "category_pcg": "615", "category_label": "Services numeriques", "business_personal": "business", "tva_deductible": True, "vendor_type": "saas"},
    {"pattern": r"SLACK|NOTION|FIGMA|GITHUB|GITLAB|JETBRAINS|CURSOR|ANTHROPIC", "category_pcg": "615", "category_label": "Services numeriques", "business_personal": "business", "tva_deductible": True, "vendor_type": "saas"},
    {"pattern": r"SHOPIFY|STRIPE|PAYPAL\s+FEE", "category_pcg": "615", "category_label": "Services numeriques", "business_personal": "business", "tva_deductible": True, "vendor_type": "saas"},

    # Transport
    {"pattern": r"SNCF|TRAINLINE|OUIGO|TGV|THALYS", "category_pcg": "625", "category_label": "Deplacements", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "transport"},
    {"pattern": r"UBER(?!\s*EAT)|BOLT|KAPTEN|FREENOW|TAXI", "category_pcg": "625", "category_label": "Deplacements", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "transport"},
    {"pattern": r"BLABLACAR|FLIXBUS", "category_pcg": "625", "category_label": "Deplacements", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "transport"},
    {"pattern": r"RATP|NAVIGO|METRO|TRANSILIEN", "category_pcg": "625", "category_label": "Deplacements", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "transport"},
    {"pattern": r"TOTAL\s+ENERGIES|SHELL|BP\s+STATION|ESSO|LECLERC\s+STATION", "category_pcg": "625", "category_label": "Deplacements", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "fuel"},

    # Food delivery / Restaurants
    {"pattern": r"UBER\s*EAT|UBEREATS", "category_pcg": "625", "category_label": "Frais de repas", "business_personal": "personal", "tva_deductible": False, "vendor_type": "food_delivery"},
    {"pattern": r"ALLORESTO|DELIVEROO|JUST\s*EAT|DOORDASH|DOMINO", "category_pcg": "625", "category_label": "Frais de repas", "business_personal": "personal", "tva_deductible": False, "vendor_type": "food_delivery"},
    {"pattern": r"MCDO|MCDONALD|BURGER\s*KING|KFC|SUBWAY|FIVE\s*GUYS", "category_pcg": "625", "category_label": "Frais de repas", "business_personal": "personal", "tva_deductible": False, "vendor_type": "fast_food"},

    # Bars
    {"pattern": r"HALL.?S\s*BEER|O.?SULLIVAN|PUB|BAR\s|BOOTLAGER", "category_pcg": "625", "category_label": "Frais de repas", "business_personal": "personal", "tva_deductible": False, "vendor_type": "bar"},

    # Groceries / Supermarkets
    {"pattern": r"MONOPRIX|CARREFOUR|FRANPRIX|INTERMARCHE|LIDL|AUCHAN|LECLERC|CASINO|PICARD|BIOCOOP", "category_pcg": "606", "category_label": "Achats non stockes", "business_personal": "personal", "tva_deductible": False, "vendor_type": "groceries"},

    # Healthcare
    {"pattern": r"DOCTEUR|DR\s|PHARMACIE|HOPITAL|CHU|CLINIQUE|DENTISTE|OPHTAL|KINE|DOCTOLIB", "category_pcg": "606", "category_label": "Frais medicaux", "business_personal": "personal", "tva_deductible": False, "vendor_type": "healthcare"},

    # Banking fees
    {"pattern": r"FRAIS\s*(DE\s*)?(TENUE|COMPTE)|COMMISSION|AGIOS|COTISATION\s*CARTE|ASSURANCE\s*CARTE", "category_pcg": "627", "category_label": "Services bancaires", "business_personal": "business", "tva_deductible": False, "vendor_type": "banking_fee"},
    {"pattern": r"BNP\s*PARIBAS|SOCIETE\s*GENERALE|LA\s*BANQUE\s*POSTALE|CREDIT\s*(MUTUEL|AGRICOLE)", "category_pcg": "627", "category_label": "Services bancaires", "business_personal": "unknown", "tva_deductible": False, "vendor_type": "banking"},

    # Telecom
    {"pattern": r"FREE\s*MOBILE|SFR|ORANGE|BOUYGUES|B&YOU", "category_pcg": "626", "category_label": "Frais postaux et telecom", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "telecom"},
    {"pattern": r"HOSTINGER|GANDI|OVH|IONOS|NAMECHEAP", "category_pcg": "626", "category_label": "Frais postaux et telecom", "business_personal": "business", "tva_deductible": True, "vendor_type": "hosting"},

    # Subscriptions / Entertainment
    {"pattern": r"NETFLIX|SPOTIFY|DEEZER|DISNEY\s*PLUS|APPLE\s*(TV|MUSIC|ONE)|YOUTUBE\s*PREMIUM|CRUNCHYROLL|PRIME\s*VIDEO", "category_pcg": "628", "category_label": "Abonnements divers", "business_personal": "personal", "tva_deductible": False, "vendor_type": "entertainment"},
    {"pattern": r"PROTON|NORDVPN|1PASSWORD|BITWARDEN|MALWAREBYTES", "category_pcg": "615", "category_label": "Services numeriques", "business_personal": "unknown", "tva_deductible": True, "vendor_type": "security_tool"},

    # Housing / Insurance
    {"pattern": r"LOYER|EDF|ENGIE|VEOLIA|SUEZ|GAZ\s*DE\s*FRANCE", "category_pcg": "613", "category_label": "Locations et charges", "business_personal": "personal", "tva_deductible": False, "vendor_type": "housing"},
    {"pattern": r"AXA|MAIF|MACIF|ALLIANZ|MATMUT|GROUPAMA|MMA|GENERALI", "category_pcg": "616", "category_label": "Assurances", "business_personal": "unknown", "tva_deductible": False, "vendor_type": "insurance"},

    # Salary (income)
    {"pattern": r"SALAIRE|VIR\s*SALAIRE|REMUNERATION|PAIE", "category_pcg": "791", "category_label": "Salaire", "business_personal": "business", "tva_deductible": False, "vendor_type": "salary"},

    # Card settlement (ignore)
    {"pattern": r"DEBIT\s*MENSUEL\s*CARTE", "category_pcg": "", "category_label": "Reglement carte", "business_personal": "unknown", "tva_deductible": False, "vendor_type": "card_settlement"},
]

# Pre-compile patterns
_COMPILED_RULES = [(re.compile(r["pattern"], re.IGNORECASE), r) for r in VENDOR_RULES]


def classify_wording(text):
    """Classify a bank transaction wording. Returns rule dict or None."""
    if not text:
        return None
    for pattern, rule in _COMPILED_RULES:
        if pattern.search(text):
            return {
                "category_pcg": rule["category_pcg"],
                "category_label": rule["category_label"],
                "business_personal": rule["business_personal"],
                "tva_deductible": rule["tva_deductible"],
                "vendor_type": rule["vendor_type"],
            }
    return None
