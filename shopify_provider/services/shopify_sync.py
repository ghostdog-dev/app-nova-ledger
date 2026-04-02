import logging
import re
import time
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import ShopifyConnection, ShopifyOrder

logger = logging.getLogger(__name__)


class ShopifyClient:
    """Thin wrapper around the Shopify Admin REST API using httpx."""

    def __init__(self, store_name: str, access_token: str):
        self.store_name = store_name
        self.access_token = access_token
        base_url = f'https://{store_name}.myshopify.com/admin/api/2024-01'
        self.client = httpx.Client(
            base_url=base_url,
            headers={
                'X-Shopify-Access-Token': access_token,
                'Content-Type': 'application/json',
            },
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def _handle_rate_limit(self, resp: httpx.Response):
        """Check rate limit headers and sleep if needed.

        Shopify uses leaky bucket (40 max, 2/sec restore).
        Header: X-Shopify-Shop-Api-Call-Limit: "32/40"
        """
        limit_header = resp.headers.get('X-Shopify-Shop-Api-Call-Limit', '')
        if limit_header:
            try:
                current, maximum = limit_header.split('/')
                if int(current) >= int(maximum) - 2:
                    time.sleep(1.0)
            except (ValueError, TypeError):
                pass

    def _request_with_retry(self, method: str, url: str, **kwargs) -> httpx.Response:
        """Make a request with 429 retry handling."""
        for attempt in range(3):
            resp = self.client.request(method, url, **kwargs)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get('Retry-After', '2.0'))
                logger.warning('Shopify 429 rate limited, sleeping %.1fs (attempt %d)', retry_after, attempt + 1)
                time.sleep(retry_after)
                continue
            self._handle_rate_limit(resp)
            resp.raise_for_status()
            return resp
        # Final attempt without catch
        resp = self.client.request(method, url, **kwargs)
        resp.raise_for_status()
        return resp

    def get_shop(self) -> dict:
        """GET /shop.json -- verify credentials and get shop info."""
        resp = self._request_with_retry('GET', '/shop.json')
        return resp.json().get('shop', {})

    def _paginate(self, endpoint: str, resource_key: str, params: dict | None = None) -> list[dict]:
        """Handle Shopify cursor-based pagination via Link header.

        Shopify returns rel="next" in Link header for next page.
        Uses limit=250 (max allowed).
        """
        results = []
        url = endpoint
        current_params = params or {}
        current_params.setdefault('limit', 250)

        while url:
            resp = self._request_with_retry('GET', url, params=current_params)
            data = resp.json()

            items = data.get(resource_key, [])
            results.extend(items)

            # Parse Link header for rel="next"
            link_header = resp.headers.get('Link', '')
            next_url = self._parse_next_link(link_header)
            if next_url:
                # Next URL is absolute — extract path + query
                url = next_url
                current_params = None  # params already in URL
            else:
                url = None

        return results

    @staticmethod
    def _parse_next_link(link_header: str) -> str | None:
        """Parse Link header to extract rel="next" URL.

        Format: <https://...>; rel="next", <https://...>; rel="previous"
        """
        if not link_header:
            return None
        match = re.search(r'<([^>]+)>;\s*rel="next"', link_header)
        return match.group(1) if match else None

    def list_orders(self, created_at_min: str | None = None, status: str = 'any') -> list[dict]:
        """List orders. IMPORTANT: default is 'open' only, must pass status=any."""
        params = {'status': status}
        if created_at_min:
            params['created_at_min'] = created_at_min
        return self._paginate('/orders.json', 'orders', params=params)


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from Shopify."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _extract_transaction_id(order: dict) -> str:
    """Extract external transaction ID from order note_attributes / meta_data.

    Looks for Stripe charge IDs and similar in note_attributes.
    """
    note_attributes = order.get('note_attributes', []) or []
    for attr in note_attributes:
        name = (attr.get('name') or '').lower()
        value = attr.get('value', '') or ''
        if name in ('_stripe_charge_id', 'stripe_charge_id', 'charge_id', 'transaction_id'):
            return value

    # Also check payment_gateway_names for correlation
    return ''


def _extract_customer_info(order: dict) -> tuple[str, str]:
    """Extract customer name and email from order."""
    customer = order.get('customer') or {}
    name_parts = [customer.get('first_name', ''), customer.get('last_name', '')]
    customer_name = ' '.join(p for p in name_parts if p).strip()
    customer_email = customer.get('email', '') or order.get('email', '') or ''
    return customer_name, customer_email


def _total_shipping(order: dict) -> Decimal:
    """Sum shipping line prices from order."""
    shipping_lines = order.get('shipping_lines', []) or []
    total = Decimal('0')
    for line in shipping_lines:
        total += Decimal(line.get('price', '0'))
    return total


def sync_shopify_data(user, days_back: int = 90) -> dict:
    """Sync Shopify orders for a user. Returns stats dict."""
    try:
        connection = user.shopify_connection
    except ShopifyConnection.DoesNotExist:
        raise ValueError('No Shopify connection found for this user')

    if not connection.is_active:
        raise ValueError('Shopify connection is inactive')

    client = ShopifyClient(connection.store_name, connection.access_token)
    stats = {'orders': 0}

    try:
        # Calculate date range
        created_at_min = (timezone.now() - timedelta(days=days_back)).isoformat()

        # Sync orders
        try:
            stats['orders'] = _sync_orders(client, user, connection, created_at_min)
        except Exception:
            logger.exception('Failed to sync Shopify orders for %s', user.email)
            stats['orders_error'] = 'Failed to sync orders'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info('Shopify sync for %s: %d orders', user.email, stats['orders'])
    return stats


def _sync_orders(client: ShopifyClient, user, connection: ShopifyConnection, created_at_min: str) -> int:
    """Sync orders from Shopify. Returns count of new/updated orders."""
    raw_orders = client.list_orders(created_at_min=created_at_min, status='any')
    count = 0

    for o in raw_orders:
        customer_name, customer_email = _extract_customer_info(o)
        transaction_id = _extract_transaction_id(o)
        total_shipping = _total_shipping(o)

        # Payment gateway — first in list
        gateways = o.get('payment_gateway_names', []) or []
        payment_gateway = gateways[0] if gateways else ''

        ShopifyOrder.objects.update_or_create(
            shopify_id=o['id'],
            defaults={
                'user': user,
                'connection': connection,
                'order_number': o.get('order_number', 0),
                'name': o.get('name', ''),
                'email': o.get('email', '') or '',
                'financial_status': o.get('financial_status', '') or '',
                'fulfillment_status': o.get('fulfillment_status') or '',
                'status': o.get('status', '') or '',  # Shopify has a cancelled_at but status is open/closed/cancelled
                'currency': o.get('currency', ''),
                'subtotal_price': Decimal(o.get('subtotal_price', '0')),
                'total_tax': Decimal(o.get('total_tax', '0')),
                'total_discounts': Decimal(o.get('total_discounts', '0')),
                'total_shipping': total_shipping,
                'total_price': Decimal(o.get('total_price', '0')),
                'payment_gateway': payment_gateway,
                'transaction_id_external': transaction_id,
                'customer_name': customer_name,
                'customer_email': customer_email,
                'line_items': o.get('line_items', []),
                'shipping_lines': o.get('shipping_lines', []),
                'tax_lines': o.get('tax_lines', []),
                'refunds': o.get('refunds', []),
                'note': o.get('note', '') or '',
                'tags': o.get('tags', '') or '',
                'created_at_shopify': _parse_dt(o['created_at']),
                'updated_at_shopify': _parse_dt(o.get('updated_at')),
                'raw_data': o,
            },
        )
        count += 1

    return count
