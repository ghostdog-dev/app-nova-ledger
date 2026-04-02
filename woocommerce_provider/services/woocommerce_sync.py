import logging
from datetime import datetime, timedelta
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import WooCommerceConnection, WooCommerceOrder

logger = logging.getLogger(__name__)


class WooCommerceClient:
    """Thin wrapper around the WooCommerce REST API v3 using httpx."""

    def __init__(self, shop_url: str, consumer_key: str, consumer_secret: str):
        base_url = shop_url.rstrip('/') + '/wp-json/wc/v3'
        self.client = httpx.Client(
            base_url=base_url,
            auth=(consumer_key, consumer_secret),
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def get_system_status(self) -> dict:
        """GET /wp-json/wc/v3/system_status -- verify credentials and get shop info."""
        resp = self.client.get('/system_status')
        resp.raise_for_status()
        return resp.json()

    def list_orders(self, after: str | None = None, status: str | None = None) -> list[dict]:
        """Fetch all orders with page-based pagination.

        Args:
            after: ISO 8601 date string to filter orders created after this date.
            status: Order status filter (e.g. 'completed', 'processing').
        """
        all_orders = []
        page = 1
        per_page = 100

        while True:
            params: dict = {'page': page, 'per_page': per_page}
            if after:
                params['after'] = after
            if status:
                params['status'] = status

            resp = self.client.get('/orders', params=params)
            resp.raise_for_status()

            orders = resp.json()
            all_orders.extend(orders)

            # Check pagination headers
            total_pages = int(resp.headers.get('X-WP-TotalPages', '1'))
            if page >= total_pages:
                break
            page += 1

        return all_orders


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO 8601 datetime string from WooCommerce (no timezone info)."""
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_decimal(value: str | None, default: Decimal = Decimal('0')) -> Decimal:
    """Parse decimal string from WooCommerce (e.g. '19.00')."""
    if not value:
        return default
    try:
        return Decimal(value)
    except Exception:
        return default


def _compute_subtotal(line_items: list[dict]) -> Decimal:
    """Sum line item subtotals."""
    total = Decimal('0')
    for item in line_items:
        total += _parse_decimal(item.get('subtotal'))
    return total


def sync_woocommerce_data(user, days_back: int = 90) -> dict:
    """Sync WooCommerce orders for a user. Returns stats dict."""
    try:
        connection = user.woocommerce_connection
    except WooCommerceConnection.DoesNotExist:
        raise ValueError('No WooCommerce connection found for this user')

    if not connection.is_active:
        raise ValueError('WooCommerce connection is inactive')

    client = WooCommerceClient(
        shop_url=connection.shop_url,
        consumer_key=connection.consumer_key,
        consumer_secret=connection.consumer_secret,
    )
    stats = {'orders': 0}

    try:
        # Calculate the "after" date
        after_date = (timezone.now() - timedelta(days=days_back)).strftime('%Y-%m-%dT%H:%M:%S')

        try:
            stats['orders'] = _sync_orders(client, user, connection, after=after_date)
        except Exception:
            logger.exception('Failed to sync WooCommerce orders for %s', user.email)
            stats['orders_error'] = 'Failed to sync orders'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info('WooCommerce sync for %s: %d orders', user.email, stats['orders'])
    return stats


def _sync_orders(client: WooCommerceClient, user, connection: WooCommerceConnection, after: str | None = None) -> int:
    """Sync orders from WooCommerce. Returns count of new/updated orders."""
    raw_orders = client.list_orders(after=after)
    count = 0

    for o in raw_orders:
        billing = o.get('billing', {}) or {}
        billing_name_parts = [billing.get('first_name', ''), billing.get('last_name', '')]
        billing_name = ' '.join(p for p in billing_name_parts if p)

        WooCommerceOrder.objects.update_or_create(
            woo_id=o['id'],
            defaults={
                'user': user,
                'connection': connection,
                'order_number': str(o.get('number', o['id'])),
                'status': o.get('status', ''),
                'currency': o.get('currency', ''),
                'subtotal_price': _compute_subtotal(o.get('line_items', [])),
                'total_tax': _parse_decimal(o.get('total_tax')),
                'total_shipping': _parse_decimal(o.get('shipping_total')),
                'total_discount': _parse_decimal(o.get('discount_total')),
                'total_price': _parse_decimal(o.get('total')),
                'payment_method': o.get('payment_method', ''),
                'payment_method_title': o.get('payment_method_title', ''),
                'transaction_id': o.get('transaction_id', ''),
                'customer_id_woo': o.get('customer_id') or None,
                'billing_email': billing.get('email', ''),
                'billing_name': billing_name,
                'line_items': o.get('line_items', []),
                'tax_lines': o.get('tax_lines', []),
                'shipping_lines': o.get('shipping_lines', []),
                'coupon_lines': o.get('coupon_lines', []),
                'refunds_summary': o.get('refunds', []),
                'date_created': _parse_dt(o.get('date_created')),
                'date_paid': _parse_dt(o.get('date_paid')),
                'date_completed': _parse_dt(o.get('date_completed')),
                'raw_data': o,
            },
        )
        count += 1

    return count
