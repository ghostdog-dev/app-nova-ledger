import logging
from datetime import datetime, timezone

import requests
from allauth.socialaccount.models import SocialAccount, SocialToken
from django.utils import timezone as dj_timezone

from emails.models import Email
from emails.services.token_refresh import get_valid_token

logger = logging.getLogger(__name__)

GRAPH_API = 'https://graph.microsoft.com/v1.0/me'
PAGE_SIZE = 100


def _get_microsoft_token(user):
    try:
        account = SocialAccount.objects.get(user=user, provider='microsoft')
        return SocialToken.objects.get(account=account)
    except (SocialAccount.DoesNotExist, SocialToken.DoesNotExist):
        return None


def _parse_ms_datetime(dt_str):
    """Parse Microsoft Graph datetime string to datetime."""
    if not dt_str:
        return dj_timezone.now()
    # Microsoft returns ISO 8601, sometimes with Z, sometimes without
    dt_str = dt_str.replace('Z', '+00:00')
    try:
        return datetime.fromisoformat(dt_str)
    except ValueError:
        return dj_timezone.now()


def _fetch_folder(user, access_token, folder, existing_ids, max_pages=None, since_date=None):
    """Fetch emails from a specific Microsoft mail folder."""
    headers = {'Authorization': f'Bearer {access_token}'}
    new_emails = []

    date_filter = ''
    if since_date:
        date_filter = f"&$filter=receivedDateTime ge {since_date}T00:00:00Z"

    url = (
        f'{GRAPH_API}/mailFolders/{folder}/messages'
        f'?$top={PAGE_SIZE}'
        f'&$select=id,subject,from,receivedDateTime,bodyPreview,hasAttachments,categories,inferenceClassification,internetMessageHeaders'
        f'&$orderby=receivedDateTime desc'
        f'{date_filter}'
    )

    pages_fetched = 0

    while url:
        resp = requests.get(url, headers=headers)
        if resp.status_code != 200:
            logger.error(f'Microsoft {folder} fetch failed: {resp.status_code} {resp.text[:200]}')
            break

        data = resp.json()
        messages = data.get('value', [])

        if not messages:
            break

        for msg in messages:
            msg_id = msg.get('id', '')
            if msg_id in existing_ids:
                continue

            from_data = msg.get('from', {}).get('emailAddress', {})

            # Detect List-Unsubscribe in internet message headers
            has_list_unsubscribe = False
            internet_headers = msg.get('internetMessageHeaders', [])
            if internet_headers:
                for header in internet_headers:
                    if header.get('name', '').lower() == 'list-unsubscribe':
                        has_list_unsubscribe = True
                        break

            new_emails.append(Email(
                user=user,
                provider=Email.Provider.MICROSOFT,
                message_id=msg_id,
                from_address=from_data.get('address', ''),
                from_name=from_data.get('name', ''),
                subject=msg.get('subject', ''),
                snippet=msg.get('bodyPreview', ''),
                date=_parse_ms_datetime(msg.get('receivedDateTime')),
                labels=msg.get('categories', []),
                has_attachments=msg.get('hasAttachments', False),
                has_list_unsubscribe=has_list_unsubscribe,
                status=Email.Status.NEW,
            ))

        pages_fetched += 1
        url = data.get('@odata.nextLink')

        if max_pages and pages_fetched >= max_pages:
            break

    return new_emails


def fetch_emails(user, max_pages=None, since_date=None):
    """
    Fetch emails from Microsoft Graph API.
    Fetches from Inbox and SentItems, excludes JunkEmail by targeting specific folders.
    Args:
        since_date: Optional date string (YYYY-MM-DD). Defaults to 30 days ago.
    Returns count of new emails saved.
    """
    access_token = get_valid_token(user, 'microsoft')
    if not access_token:
        logger.info(f'No valid Microsoft token for user {user.pk}')
        return 0

    # Default to 30 days ago
    if not since_date:
        from datetime import timedelta
        since_date = (dj_timezone.now() - timedelta(days=30)).strftime('%Y-%m-%d')

    # Get existing message IDs for dedup
    existing_ids = set(
        Email.objects.filter(user=user, provider='microsoft')
        .values_list('message_id', flat=True)
    )

    all_new_emails = []

    # Fetch from Inbox (excludes JunkEmail, Deleted Items, etc.)
    all_new_emails.extend(_fetch_folder(user, access_token, 'inbox', existing_ids, max_pages, since_date))

    # Also fetch SentItems (useful for sent invoices)
    all_new_emails.extend(_fetch_folder(user, access_token, 'sentitems', existing_ids, max_pages, since_date))

    # Bulk create, skip duplicates
    if all_new_emails:
        Email.objects.bulk_create(all_new_emails, ignore_conflicts=True)

    logger.info(f'Microsoft: fetched {len(all_new_emails)} new emails for user {user.pk}')
    return len(all_new_emails)
