"""
Seed test data on connected providers (Stripe, PayPal, Mollie) for user 13.

Creates real test-mode objects via each provider's API, then triggers a sync
to pull them into our DB.

Usage:
    python manage.py seed_provider_data
"""

import logging
import time

import httpx
import stripe

from django.core.management.base import BaseCommand

from accounts.models import CustomUser

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Seed test data on connected providers (Stripe, PayPal, Mollie)'

    def handle(self, *args, **options):
        user = CustomUser.objects.get(pk=13)
        self.stdout.write(f'Seeding test data for user: {user.email}')

        self._seed_stripe(user)
        self._seed_paypal(user)
        self._seed_mollie(user)

        self.stdout.write(self.style.SUCCESS('Done.'))

    # -----------------------------------------------------------------------
    # Stripe
    # -----------------------------------------------------------------------
    def _seed_stripe(self, user):
        from stripe_provider.models import StripeConnection
        from stripe_provider.services.stripe_sync import sync_stripe_data

        try:
            conn = StripeConnection.objects.get(user=user)
        except StripeConnection.DoesNotExist:
            self.stdout.write(self.style.WARNING('Stripe: not connected, skipping.'))
            return

        api_key = conn.access_token
        self.stdout.write('Stripe: creating test data...')

        # -- Create a test customer --
        customer = stripe.Customer.create(
            api_key=api_key,
            email='test-seed@example.com',
            name='Seed Test Customer',
        )
        cid = customer.id
        self.stdout.write(f'  Customer: {cid}')

        # Attach a test payment method to the customer
        pm = stripe.PaymentMethod.attach(
            'pm_card_visa',
            api_key=api_key,
            customer=cid,
        )
        stripe.Customer.modify(
            cid,
            api_key=api_key,
            invoice_settings={'default_payment_method': pm.id},
        )

        # -- 5 charges with different amounts --
        charge_amounts = [1500, 2999, 500, 7850, 12000]  # cents
        for i, amount in enumerate(charge_amounts, 1):
            pi = stripe.PaymentIntent.create(
                api_key=api_key,
                amount=amount,
                currency='eur',
                customer=cid,
                payment_method=pm.id,
                confirm=True,
                automatic_payment_methods={'enabled': True, 'allow_redirects': 'never'},
                description=f'Seed charge #{i}',
            )
            self.stdout.write(f'  Charge #{i}: {pi.latest_charge} ({amount / 100:.2f} EUR)')

        # -- 2 refunds (on the first two charges) --
        # Retrieve the charges we just created
        charges = stripe.Charge.list(api_key=api_key, customer=cid, limit=5)
        for i, ch in enumerate(charges.data[:2], 1):
            refund = stripe.Refund.create(
                api_key=api_key,
                charge=ch.id,
                amount=ch.amount // 2,  # partial refund
            )
            self.stdout.write(f'  Refund #{i}: {refund.id} ({ch.amount // 200:.0f}.{(ch.amount // 2) % 100:02d} EUR on {ch.id})')

        # -- 3 invoices with line items --
        product = stripe.Product.create(
            api_key=api_key,
            name='Seed Test Product',
        )
        prices = []
        for amount in [2000, 4500, 9900]:  # cents
            price = stripe.Price.create(
                api_key=api_key,
                product=product.id,
                unit_amount=amount,
                currency='eur',
            )
            prices.append(price)

        for i, price in enumerate(prices, 1):
            inv = stripe.Invoice.create(
                api_key=api_key,
                customer=cid,
                auto_advance=True,
            )
            stripe.InvoiceItem.create(
                api_key=api_key,
                customer=cid,
                invoice=inv.id,
                price=price.id,
                quantity=i,  # 1, 2, 3 items
            )
            # Add a second line item for variety
            stripe.InvoiceItem.create(
                api_key=api_key,
                customer=cid,
                invoice=inv.id,
                price=prices[0].id,
                quantity=1,
            )
            finalized = stripe.Invoice.finalize_invoice(inv.id, api_key=api_key)
            paid = stripe.Invoice.pay(finalized.id, api_key=api_key)
            self.stdout.write(f'  Invoice #{i}: {paid.id} ({paid.total / 100:.2f} EUR)')

        # -- 1 subscription --
        sub_price = stripe.Price.create(
            api_key=api_key,
            product=product.id,
            unit_amount=1990,
            currency='eur',
            recurring={'interval': 'month'},
        )
        sub = stripe.Subscription.create(
            api_key=api_key,
            customer=cid,
            items=[{'price': sub_price.id}],
        )
        self.stdout.write(f'  Subscription: {sub.id} (19.90 EUR/month)')

        # -- Sync --
        self.stdout.write('Stripe: syncing...')
        stats = sync_stripe_data(user, days_back=1)
        self.stdout.write(self.style.SUCCESS(f'Stripe: sync complete. {stats}'))

    # -----------------------------------------------------------------------
    # PayPal
    # -----------------------------------------------------------------------
    def _seed_paypal(self, user):
        from paypal_provider.models import PayPalConnection
        from paypal_provider.services.paypal_sync import sync_paypal_data

        try:
            conn = PayPalConnection.objects.get(user=user)
        except PayPalConnection.DoesNotExist:
            self.stdout.write(self.style.WARNING('PayPal: not connected, skipping.'))
            return

        base_url = 'https://api-m.sandbox.paypal.com' if conn.is_sandbox else 'https://api-m.paypal.com'
        self.stdout.write('PayPal: getting access token...')

        # Get OAuth token
        with httpx.Client(timeout=30) as client:
            token_resp = client.post(
                f'{base_url}/v1/oauth2/token',
                auth=(conn.client_id, conn.client_secret),
                data={'grant_type': 'client_credentials'},
            )
            token_resp.raise_for_status()
            access_token = token_resp.json()['access_token']

        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }

        self.stdout.write('PayPal: creating test data...')

        with httpx.Client(timeout=30, headers=headers, base_url=base_url) as client:
            # -- 3 orders (create + capture) --
            order_amounts = ['25.00', '89.99', '150.00']
            for i, amount in enumerate(order_amounts, 1):
                order_body = {
                    'intent': 'CAPTURE',
                    'purchase_units': [{
                        'reference_id': f'seed-order-{i}-{int(time.time())}',
                        'description': f'Seed test order #{i}',
                        'amount': {
                            'currency_code': 'EUR',
                            'value': amount,
                            'breakdown': {
                                'item_total': {'currency_code': 'EUR', 'value': amount},
                            },
                        },
                        'items': [{
                            'name': f'Test Item {i}',
                            'quantity': '1',
                            'unit_amount': {'currency_code': 'EUR', 'value': amount},
                        }],
                    }],
                    'payment_source': {
                        'paypal': {
                            'experience_context': {
                                'return_url': 'https://example.com/return',
                                'cancel_url': 'https://example.com/cancel',
                            },
                        },
                    },
                }
                resp = client.post('/v2/checkout/orders', json=order_body)
                if resp.status_code in (200, 201):
                    order_id = resp.json()['id']
                    self.stdout.write(f'  Order #{i}: {order_id} ({amount} EUR)')
                    # Try to capture (may need buyer approval in sandbox)
                    cap_resp = client.post(f'/v2/checkout/orders/{order_id}/capture')
                    if cap_resp.status_code in (200, 201):
                        self.stdout.write(f'    Captured: {order_id}')
                    else:
                        self.stdout.write(f'    Capture pending (needs buyer approval): {cap_resp.status_code}')
                else:
                    self.stdout.write(self.style.WARNING(f'  Order #{i} failed: {resp.status_code} {resp.text[:200]}'))

            # -- 1 invoice --
            invoice_body = {
                'detail': {
                    'invoice_number': f'SEED-INV-{int(time.time())}',
                    'currency_code': 'EUR',
                    'note': 'Seed test invoice',
                    'payment_term': {'term_type': 'NET_30'},
                },
                'primary_recipients': [{
                    'billing_info': {
                        'email_address': 'sb-buyer@personal.example.com',
                        'name': {'given_name': 'Test', 'surname': 'Buyer'},
                    },
                }],
                'items': [
                    {
                        'name': 'Consulting Service',
                        'quantity': '2',
                        'unit_amount': {'currency_code': 'EUR', 'value': '75.00'},
                    },
                    {
                        'name': 'Setup Fee',
                        'quantity': '1',
                        'unit_amount': {'currency_code': 'EUR', 'value': '50.00'},
                    },
                ],
            }
            resp = client.post('/v2/invoicing/invoices', json=invoice_body)
            if resp.status_code in (200, 201):
                inv_href = resp.json().get('href', '')
                inv_id = inv_href.split('/')[-1] if inv_href else resp.json().get('id', '?')
                self.stdout.write(f'  Invoice: {inv_id} (200.00 EUR)')
                # Send the invoice
                send_resp = client.post(f'/v2/invoicing/invoices/{inv_id}/send', json={})
                if send_resp.status_code in (200, 202):
                    self.stdout.write(f'    Invoice sent.')
                else:
                    self.stdout.write(f'    Invoice send: {send_resp.status_code}')
            else:
                self.stdout.write(self.style.WARNING(f'  Invoice failed: {resp.status_code} {resp.text[:200]}'))

        # -- Sync --
        self.stdout.write('PayPal: syncing...')
        stats = sync_paypal_data(user, days_back=1)
        self.stdout.write(self.style.SUCCESS(f'PayPal: sync complete. {stats}'))

    # -----------------------------------------------------------------------
    # Mollie
    # -----------------------------------------------------------------------
    def _seed_mollie(self, user):
        from mollie_provider.models import MollieConnection
        from mollie_provider.services.mollie_sync import sync_mollie_data

        try:
            conn = MollieConnection.objects.get(user=user)
        except MollieConnection.DoesNotExist:
            self.stdout.write(self.style.WARNING('Mollie: not connected, skipping.'))
            return

        api_key = conn.api_key
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }

        self.stdout.write('Mollie: creating test payments...')

        payment_configs = [
            {'amount': '10.00', 'description': 'Seed payment #1 - Small order'},
            {'amount': '49.99', 'description': 'Seed payment #2 - Medium order'},
            {'amount': '125.00', 'description': 'Seed payment #3 - Large order'},
            {'amount': '9.90', 'description': 'Seed payment #4 - Subscription'},
            {'amount': '250.00', 'description': 'Seed payment #5 - Premium order'},
        ]

        with httpx.Client(timeout=30, headers=headers) as client:
            for i, cfg in enumerate(payment_configs, 1):
                body = {
                    'amount': {
                        'currency': 'EUR',
                        'value': cfg['amount'],
                    },
                    'description': cfg['description'],
                    'redirectUrl': 'https://example.com/return',
                    'metadata': {
                        'seed': True,
                        'order_nr': f'SEED-{i}-{int(time.time())}',
                    },
                }
                resp = client.post('https://api.mollie.com/v2/payments', json=body)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    self.stdout.write(f'  Payment #{i}: {data["id"]} ({cfg["amount"]} EUR, status={data["status"]})')
                else:
                    self.stdout.write(self.style.WARNING(f'  Payment #{i} failed: {resp.status_code} {resp.text[:200]}'))

        # -- Sync --
        self.stdout.write('Mollie: syncing...')
        stats = sync_mollie_data(user)
        self.stdout.write(self.style.SUCCESS(f'Mollie: sync complete. {stats}'))
