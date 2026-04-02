"""Enrich bank transactions with categories, business/personal, vendor type, and recurring detection."""
import logging
from django.utils import timezone
from banking.models import BankTransaction
from banking.services.recurring import detect_recurring

logger = logging.getLogger(__name__)


def enrich_transactions(user, force=False):
    """
    Enrich bank transactions with expense category, business/personal, TVA, vendor type.
    Uses AI classification (with regex fallback). Also runs recurring detection.
    Returns stats dict.
    """
    # AI classification (handles its own fallback to regex)
    from ai_agent.services.classification import classify_bank_transactions
    classification_stats = classify_bank_transactions(user, force=force)

    # Run recurring detection
    recurring_stats = detect_recurring(user)

    return {
        **classification_stats,
        **recurring_stats,
    }
