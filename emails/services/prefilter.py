import logging

from emails.models import Email

logger = logging.getLogger(__name__)

# Domains that NEVER send transactional emails (invoices, receipts, orders).
# Be conservative: if a domain might ever send a receipt or payment confirmation, do NOT add it here.
NON_TRANSACTIONAL_DOMAINS = {
    # Social / professional
    'linkedin.com',
    'github.com',
    # Education / courses
    'codecademy.com',
    'openclassrooms.com',
    'magicschool.ai',
    'codingame.com',
    # Job boards
    'hellowork.com',
    'free-work.com',
    'externatic.fr',
    # Dev tools newsletters (never send invoices)
    'whimsical.com',
    'codepen.io',
    'cursor.com',
    'claude.com',
    'bubble.io',
    'render.com',
    'lovable.dev',
    'uxpilot.ai',
    'figma.com',
    # Creative / media
    'artlist.io',
    'dribbble.com',
    'pixlr.com',
    # Entertainment / streaming
    'crunchyroll.com',
    'tf1.fr',
    'primevideo.com',
    # Gaming promos (not transactions)
    'instant-gaming.com',
    '1kamas.com',
    # Security / misc
    'malwarebytes.com',
    'wetransfer.com',
    'trustpilotmail.com',
    'staycation.co',
    'nordpass.com',
}

# Gmail labels that indicate non-transactional categories
NON_TRANSACTIONAL_LABELS = {
    'CATEGORY_PROMOTIONS',
    'CATEGORY_SOCIAL',
    'CATEGORY_FORUMS',
}


def _extract_domain(from_address):
    """Extract the domain from an email address (e.g., 'user@sub.linkedin.com' -> 'linkedin.com')."""
    if not from_address or '@' not in from_address:
        return ''
    raw_domain = from_address.rsplit('@', 1)[-1].strip().lower()
    # Match against known domains including subdomains (e.g., mail.linkedin.com -> linkedin.com)
    parts = raw_domain.split('.')
    # Try progressively shorter domain suffixes: mail.sub.linkedin.com -> sub.linkedin.com -> linkedin.com
    for i in range(len(parts) - 1):
        candidate = '.'.join(parts[i:])
        if candidate in NON_TRANSACTIONAL_DOMAINS:
            return candidate
    return raw_domain


def _matches_non_transactional_domain(from_address):
    """Check if the sender domain matches one of the known non-transactional domains."""
    if not from_address or '@' not in from_address:
        return False
    raw_domain = from_address.rsplit('@', 1)[-1].strip().lower()
    parts = raw_domain.split('.')
    for i in range(len(parts) - 1):
        candidate = '.'.join(parts[i:])
        if candidate in NON_TRANSACTIONAL_DOMAINS:
            return True
    return False


def _has_non_transactional_label(labels):
    """Check if any Gmail label indicates a non-transactional category."""
    if not labels:
        return False
    return bool(NON_TRANSACTIONAL_LABELS.intersection(labels))


def prefilter_emails(user):
    """
    Rule-based pre-filter that marks obvious non-transactional emails as 'ignored'
    BEFORE sending them to the LLM for classification.

    This is intentionally conservative -- only filters emails we are confident
    are NOT transactional (no invoices, receipts, or payment confirmations).

    Returns:
        dict with keys 'auto_ignored' and 'remaining_for_ai'
    """
    new_emails = Email.objects.filter(user=user, status=Email.Status.NEW)
    total_new = new_emails.count()

    if total_new == 0:
        logger.info(f'Prefilter: no new emails to filter for user {user.pk}')
        return {'auto_ignored': 0, 'remaining_for_ai': 0}

    ids_to_ignore = []
    reasons = {}  # email_id -> reason (for logging)

    for email_obj in new_emails.iterator():
        reason = None

        # Rule A: Has List-Unsubscribe header (bulk/marketing mail)
        if email_obj.has_list_unsubscribe:
            reason = 'list-unsubscribe header'

        # Rule B: Sender domain is in the known non-transactional list
        elif _matches_non_transactional_domain(email_obj.from_address):
            domain = _extract_domain(email_obj.from_address)
            reason = f'non-transactional domain ({domain})'

        # Rule C: Gmail label indicates promotions, social, or forums
        elif _has_non_transactional_label(email_obj.labels):
            matched = NON_TRANSACTIONAL_LABELS.intersection(email_obj.labels)
            reason = f'gmail label ({", ".join(matched)})'

        if reason:
            ids_to_ignore.append(email_obj.id)
            reasons[email_obj.id] = reason

    # Bulk update to 'ignored'
    if ids_to_ignore:
        ignored_count = Email.objects.filter(id__in=ids_to_ignore).update(status=Email.Status.IGNORED)
    else:
        ignored_count = 0

    remaining = total_new - ignored_count

    # Log summary
    logger.info(
        f'Prefilter for user {user.pk}: {ignored_count} auto-ignored, '
        f'{remaining} remaining for AI (out of {total_new} new emails)'
    )

    # Log individual reasons (at debug level to avoid noise)
    for email_id, reason in reasons.items():
        logger.debug(f'  Prefilter ignored email {email_id}: {reason}')

    return {
        'auto_ignored': ignored_count,
        'remaining_for_ai': remaining,
    }
