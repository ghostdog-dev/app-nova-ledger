import email.utils
import logging
from datetime import datetime, timezone

import requests
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.utils import timezone as dj_timezone

from emails.models import Email

logger = logging.getLogger(__name__)

GMAIL_API = 'https://gmail.googleapis.com/gmail/v1/users/me'
GMAIL_EXCLUDE_QUERY = '-category:promotions -category:social -category:forums -in:spam'
BATCH_SIZE = 100  # Gmail API max per page


def _get_google_token(user):
    try:
        account = SocialAccount.objects.get(user=user, provider='google')
        return SocialToken.objects.get(account=account)
    except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
        return None


def _parse_from_header(from_raw):
    """Parse 'Display Name <email@example.com>' into (name, address)."""
    if not from_raw:
        return '', ''
    name, addr = email.utils.parseaddr(from_raw)
    return name or '', addr or from_raw


def _parse_gmail_date(internal_date_ms):
    """Convert Gmail internalDate (milliseconds since epoch) to datetime."""
    if not internal_date_ms:
        return dj_timezone.now()
    return datetime.fromtimestamp(int(internal_date_ms) / 1000, tz=timezone.utc)


def _has_attachments(payload):
    """Check if a Gmail message has attachments."""
    parts = payload.get('parts', [])
    for part in parts:
        if part.get('filename'):
            return True
        # Check nested parts
        if part.get('parts'):
            if _has_attachments(part):
                return True
    return False


def _get_header(headers, name):
    """Get a header value by name from Gmail headers list."""
    for h in headers:
        if h['name'].lower() == name.lower():
            return h['value']
    return ''


def fetch_emails(user, max_pages=None, since_date=None):
    """
    Fetch emails from Gmail API with pre-filtering.
    Args:
        since_date: Optional date string (YYYY-MM-DD). Defaults to 30 days ago.
    Returns count of new emails saved.
    """
    token = _get_google_token(user)
    if not token:
        logger.info(f'No Google token for user {user.pk}')
        return 0

    headers = {'Authorization': f'Bearer {token.token}'}

    # Default to 30 days ago
    if not since_date:
        from datetime import timedelta
        since_date = (dj_timezone.now() - timedelta(days=30)).strftime('%Y/%m/%d')
    else:
        # Convert YYYY-MM-DD to YYYY/MM/DD for Gmail
        since_date = since_date.replace('-', '/')

    # Get existing message IDs for dedup
    existing_ids = set(
        Email.objects.filter(user=user, provider='google')
        .values_list('message_id', flat=True)
    )

    new_emails = []
    page_token = None
    pages_fetched = 0

    while True:
        # List messages with pre-filter query + date
        params = {
            'q': f'{GMAIL_EXCLUDE_QUERY} after:{since_date}',
            'maxResults': BATCH_SIZE,
        }
        if page_token:
            params['pageToken'] = page_token

        resp = requests.get(f'{GMAIL_API}/messages', headers=headers, params=params)
        if resp.status_code != 200:
            logger.error(f'Gmail list messages failed: {resp.status_code} {resp.text[:200]}')
            break

        data = resp.json()
        messages = data.get('messages', [])

        if not messages:
            break

        # Filter out already fetched messages
        new_message_ids = [m['id'] for m in messages if m['id'] not in existing_ids]

        # Fetch metadata for each new message
        for msg_id in new_message_ids:
            detail_resp = requests.get(
                f'{GMAIL_API}/messages/{msg_id}',
                headers=headers,
                params={'format': 'metadata', 'metadataHeaders': ['From', 'Subject', 'Date']},
            )
            if detail_resp.status_code != 200:
                logger.warning(f'Gmail get message {msg_id} failed: {detail_resp.status_code}')
                continue

            msg_data = detail_resp.json()
            msg_headers = msg_data.get('payload', {}).get('headers', [])
            from_raw = _get_header(msg_headers, 'From')
            from_name, from_address = _parse_from_header(from_raw)

            new_emails.append(Email(
                user=user,
                provider=Email.Provider.GOOGLE,
                message_id=msg_id,
                from_address=from_address,
                from_name=from_name,
                subject=_get_header(msg_headers, 'Subject'),
                snippet=msg_data.get('snippet', ''),
                date=_parse_gmail_date(msg_data.get('internalDate')),
                labels=msg_data.get('labelIds', []),
                has_attachments=_has_attachments(msg_data.get('payload', {})),
                status=Email.Status.NEW,
            ))

        pages_fetched += 1
        page_token = data.get('nextPageToken')

        if not page_token or (max_pages and pages_fetched >= max_pages):
            break

    # Bulk create, skip duplicates
    if new_emails:
        Email.objects.bulk_create(new_emails, ignore_conflicts=True)

    logger.info(f'Gmail: fetched {len(new_emails)} new emails for user {user.pk}')
    return len(new_emails)
