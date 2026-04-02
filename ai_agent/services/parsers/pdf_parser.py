"""
PDF bank statement parser using Claude Haiku vision.

Sends the PDF as base64 to Claude, gets back structured JSON
with bank transactions, saves them as UnifiedTransactions.

Independent from the agentic pipeline — runs at upload time.
"""
import base64
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

import anthropic
from django.conf import settings

logger = logging.getLogger(__name__)

MODEL = 'claude-haiku-4-5-20251001'

SYSTEM_PROMPT = (
    "Tu es un expert en parsing de relevés bancaires PDF. "
    "On te donne un relevé bancaire en PDF. Extrais TOUTES les lignes de transactions.\n\n"
    "Pour chaque transaction, extrais :\n"
    "- date: format YYYY-MM-DD\n"
    "- label: le libellé complet de l'opération\n"
    "- amount: le montant (négatif pour les débits, positif pour les crédits)\n"
    "- currency: devise ISO 4217 (EUR par défaut)\n\n"
    "Retourne UNIQUEMENT un JSON valide, rien d'autre.\n"
    "Si tu détectes le nom de la banque, inclus-le dans le champ 'bank_name'.\n"
    "Si tu détectes un IBAN ou numéro de compte, inclus-le dans 'account_id'."
)

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "bank_name": {"type": "string", "description": "Nom de la banque détecté"},
        "account_id": {"type": "string", "description": "IBAN ou numéro de compte"},
        "transactions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "date": {"type": "string", "description": "Date YYYY-MM-DD"},
                    "label": {"type": "string", "description": "Libellé de l'opération"},
                    "amount": {"type": "number", "description": "Montant (négatif=débit, positif=crédit)"},
                    "currency": {"type": "string", "description": "Devise ISO 4217"},
                },
                "required": ["date", "label", "amount"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["transactions"],
    "additionalProperties": False,
}


def parse_pdf_bank_statement(pdf_content: bytes) -> dict | None:
    """
    Send a PDF to Claude Haiku and get structured bank transactions back.

    Returns dict with keys: bank_name, account_id, transactions[]
    Each transaction: {date, label, amount, currency}
    Returns None on failure.
    """
    api_key = getattr(settings, 'ANTHROPIC_API_KEY', None)
    if not api_key:
        import os
        api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.error('[PDF Parser] No ANTHROPIC_API_KEY configured')
        return None

    pdf_b64 = base64.standard_b64encode(pdf_content).decode('utf-8')

    client = anthropic.Anthropic(api_key=api_key)

    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "document",
                            "source": {
                                "type": "base64",
                                "media_type": "application/pdf",
                                "data": pdf_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extrais toutes les transactions de ce relevé bancaire.",
                        },
                    ],
                }
            ],
            output_config={
                "format": {
                    "type": "json_schema",
                    "schema": OUTPUT_SCHEMA,
                }
            },
        )

        text = ''.join(
            block.text for block in response.content
            if hasattr(block, 'text') and block.text
        )

        result = json.loads(text)
        logger.info(
            f'[PDF Parser] Extracted {len(result.get("transactions", []))} transactions '
            f'from PDF (bank: {result.get("bank_name", "unknown")})'
        )
        return result

    except anthropic.APIError as e:
        logger.error(f'[PDF Parser] API error: {e}')
        return None
    except (json.JSONDecodeError, KeyError) as e:
        logger.error(f'[PDF Parser] Parse error: {e}')
        return None
    except Exception as e:
        logger.error(f'[PDF Parser] Unexpected error: {e}')
        return None
