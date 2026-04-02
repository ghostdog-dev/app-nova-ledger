import logging
from datetime import datetime
from decimal import Decimal

import httpx
from django.utils import timezone

from ..models import PrestaShopConnection, PrestaShopOrder, PrestaShopPayment

logger = logging.getLogger(__name__)

PAGE_SIZE = 50


class PrestaShopClient:
    """Thin wrapper around the PrestaShop REST API using httpx.

    Auth: HTTP Basic with api_key as username, blank password.
    All responses use ?output_format=JSON&display=full.
    Pagination: offset-based with ?limit=offset,count.
    """

    def __init__(self, shop_url: str, api_key: str):
        self.shop_url = shop_url.rstrip('/')
        self.api_key = api_key
        self.client = httpx.Client(
            base_url=f'{self.shop_url}/api',
            auth=(api_key, ''),
            timeout=30.0,
        )

    def close(self):
        self.client.close()

    def verify(self) -> dict:
        """GET /api/?output_format=JSON -- verify credentials and get shop info."""
        resp = self.client.get('/', params={'output_format': 'JSON'})
        resp.raise_for_status()
        data = resp.json()
        # PrestaShop root API returns shop name in the response
        shop_name = ''
        if isinstance(data, dict):
            api_info = data.get('api', data)
            if isinstance(api_info, dict):
                shop_name = api_info.get('shop_name', '')
        return {'shop_name': shop_name}

    def _paginate(self, endpoint: str, resource_key: str) -> list[dict]:
        """Handle PrestaShop offset-based pagination.

        Uses ?limit=offset,count. Iterates until empty array.
        """
        results = []
        offset = 0

        while True:
            resp = self.client.get(
                endpoint,
                params={
                    'output_format': 'JSON',
                    'display': 'full',
                    'limit': f'{offset},{PAGE_SIZE}',
                },
            )
            resp.raise_for_status()
            data = resp.json()

            items = data.get(resource_key, [])
            if not items:
                break

            results.extend(items)
            offset += PAGE_SIZE

            # If we got fewer than PAGE_SIZE, we've reached the end
            if len(items) < PAGE_SIZE:
                break

        return results

    def get_orders(self) -> list[dict]:
        return self._paginate('/orders', 'orders')

    def get_order_payments(self) -> list[dict]:
        return self._paginate('/order_payments', 'order_payments')


def _parse_decimal(value) -> Decimal:
    """Parse a PrestaShop string amount (e.g. '68.900000') to Decimal."""
    if value is None or value == '':
        return Decimal('0')
    return Decimal(str(value))


def _parse_int(value) -> int | None:
    """Parse a PrestaShop string ID (e.g. '5') to int."""
    if value is None or value == '':
        return None
    return int(str(value))


def _parse_dt(value) -> datetime | None:
    """Parse PrestaShop datetime string 'YYYY-MM-DD HH:MM:SS'."""
    if not value or value == '0000-00-00 00:00:00':
        return None
    return datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')


def sync_prestashop_data(user) -> dict:
    """Sync all PrestaShop data for a user. Returns stats dict."""
    try:
        connection = user.prestashop_connection
    except PrestaShopConnection.DoesNotExist:
        raise ValueError('No PrestaShop connection found for this user')

    if not connection.is_active:
        raise ValueError('PrestaShop connection is inactive')

    client = PrestaShopClient(connection.shop_url, connection.api_key)
    stats = {'orders': 0, 'payments': 0}

    try:
        # Sync orders
        try:
            stats['orders'] = _sync_orders(client, user, connection)
        except Exception:
            logger.exception('Failed to sync PrestaShop orders for %s', user.email)
            stats['orders_error'] = 'Failed to sync orders'

        # Sync payments
        try:
            stats['payments'] = _sync_payments(client, user, connection)
        except Exception:
            logger.exception('Failed to sync PrestaShop payments for %s', user.email)
            stats['payments_error'] = 'Failed to sync payments'

        # Update last_sync
        connection.last_sync = timezone.now()
        connection.save(update_fields=['last_sync'])
    finally:
        client.close()

    logger.info(
        'PrestaShop sync for %s: %d orders, %d payments',
        user.email, stats['orders'], stats['payments'],
    )
    return stats


def _sync_orders(client: PrestaShopClient, user, connection: PrestaShopConnection) -> int:
    """Sync orders from PrestaShop. Returns count of new/updated orders."""
    raw_orders = client.get_orders()
    count = 0

    for o in raw_orders:
        # Extract line items from associations.order_rows
        associations = o.get('associations', {}) or {}
        order_rows = associations.get('order_rows', []) or []

        PrestaShopOrder.objects.update_or_create(
            prestashop_id=int(str(o['id'])),
            defaults={
                'user': user,
                'connection': connection,
                'reference': str(o.get('reference', '')),
                'current_state': int(str(o.get('current_state', 0))),
                'current_state_name': str(o.get('current_state_name', '') or ''),
                'payment_method': str(o.get('payment', '') or ''),
                'payment_module': str(o.get('module', '') or ''),
                'total_paid': _parse_decimal(o.get('total_paid')),
                'total_paid_real': _parse_decimal(o.get('total_paid_real')),
                'total_products': _parse_decimal(o.get('total_products')),
                'total_products_wt': _parse_decimal(o.get('total_products_wt')),
                'total_shipping': _parse_decimal(o.get('total_shipping')),
                'total_shipping_tax_incl': _parse_decimal(o.get('total_shipping_tax_incl')),
                'total_discounts': _parse_decimal(o.get('total_discounts')),
                'currency_id': _parse_int(o.get('id_currency')),
                'customer_id_ps': _parse_int(o.get('id_customer')),
                'invoice_number': str(o.get('invoice_number', '') or ''),
                'line_items': order_rows,
                'date_add': _parse_dt(o.get('date_add')),
                'date_upd': _parse_dt(o.get('date_upd')),
                'raw_data': o,
            },
        )
        count += 1

    return count


def _sync_payments(client: PrestaShopClient, user, connection: PrestaShopConnection) -> int:
    """Sync order payments from PrestaShop. Returns count of new/updated payments."""
    raw_payments = client.get_order_payments()
    count = 0

    for p in raw_payments:
        PrestaShopPayment.objects.update_or_create(
            prestashop_id=int(str(p['id'])),
            defaults={
                'user': user,
                'connection': connection,
                'order_reference': str(p.get('order_reference', '')),
                'amount': _parse_decimal(p.get('amount')),
                'payment_method': str(p.get('payment_method', '') or ''),
                'transaction_id': str(p.get('transaction_id', '') or ''),
                'card_brand': str(p.get('card_brand', '') or ''),
                'date_add': _parse_dt(p.get('date_add')),
                'raw_data': p,
            },
        )
        count += 1

    return count
