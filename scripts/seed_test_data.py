#!/usr/bin/env python
"""
External seed script for Nova Ledger test data.
Creates provider transactions that MATCH existing email + bank data in DB.
Run from project root: python scripts/seed_test_data.py
Delete after testing.
"""
import os
import sys
from datetime import date, timedelta
from decimal import Decimal

# Django setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'nova_ledger.settings')

import django
django.setup()

from django.utils import timezone
from accounts.models import CustomUser

USER_ID = 13


def seed_stripe():
    """Create Stripe charges matching existing email transactions."""
    from stripe_provider.models import StripeConnection
    conn = StripeConnection.objects.filter(user_id=USER_ID, is_active=True).first()
    if not conn:
        print('  SKIP: not connected')
        return

    import stripe
    key = conn.access_token

    # Scenarios based on real email data in DB:
    # S01: SNCF 26.48 EUR (matches email + bank)
    # S05: Free Mobile 19.99 EUR (matches email, no bank)
    # S10: EDF 67.82 EUR failed (matches email, no bank)
    # S12: Google subscription ~93 EUR/month
    charges = [
        {'amount': 2648, 'currency': 'eur', 'desc': 'SNCF ticket Paris-Lyon', 'method': 'pm_card_visa'},
        {'amount': 1999, 'currency': 'eur', 'desc': 'Free Mobile subscription', 'method': 'pm_card_visa'},
        {'amount': 8575, 'currency': 'eur', 'desc': 'Alloresto food delivery', 'method': 'pm_card_visa'},
        {'amount': 8214, 'currency': 'eur', 'desc': 'Uber Eats order', 'method': 'pm_card_visa'},
        {'amount': 6782, 'currency': 'eur', 'desc': 'EDF electricity bill FAILED', 'method': 'pm_card_chargeDeclined'},
    ]

    for c in charges:
        try:
            pi = stripe.PaymentIntent.create(
                api_key=key,
                amount=c['amount'],
                currency=c['currency'],
                payment_method=c['method'],
                confirm=True,
                description=c['desc'],
                automatic_payment_methods={'enabled': False, 'allow_redirects': 'never'},
            )
            status = pi.status
            print(f'  Charge {c["amount"]/100:.2f} {c["currency"].upper()} "{c["desc"]}" → {status}')
        except stripe.error.CardError as e:
            print(f'  Charge {c["amount"]/100:.2f} {c["currency"].upper()} "{c["desc"]}" → DECLINED (expected)')
        except Exception as e:
            print(f'  ERROR: {e}')

    # Create a refund on the SNCF charge (S09)
    try:
        charges_list = stripe.Charge.list(api_key=key, limit=5)
        if charges_list.data:
            first = charges_list.data[0]
            stripe.Refund.create(api_key=key, charge=first.id, amount=1000)
            print(f'  Refund 10.00 EUR on charge {first.id[:20]}...')
    except Exception as e:
        print(f'  Refund ERROR: {e}')

    # Sync to pull into our DB
    from stripe_provider.services.stripe_sync import sync_stripe_data
    user = CustomUser.objects.get(pk=USER_ID)
    result = sync_stripe_data(user)
    total = sum(v.get('created', 0) if isinstance(v, dict) else 0 for v in result.values())
    print(f'  Synced: {total} records created')


def seed_stripe_bank_txs():
    """Create fake bank transactions that match Stripe payouts."""
    from banking.models import BankTransaction, BankAccount
    account = BankAccount.objects.filter(user_id=USER_ID, currency='EUR').first()
    if not account:
        print('  SKIP: no EUR bank account')
        return

    ts = int(timezone.now().timestamp())

    # S08: Stripe payout 500 EUR
    # S09: Stripe refund 10 EUR
    fake_bank = [
        {'value': Decimal('500.00'), 'wording': 'STRIPE PAYOUT', 'type': 'transfer', 'date': date(2026, 3, 28)},
        {'value': Decimal('25.00'), 'wording': 'STRIPE REFUND', 'type': 'transfer', 'date': date(2026, 3, 27)},
    ]

    for i, fb in enumerate(fake_bank):
        BankTransaction.objects.update_or_create(
            powens_transaction_id=900000 + ts + i,
            defaults={
                'account': account,
                'user_id': USER_ID,
                'date': fb['date'],
                'rdate': fb['date'],
                'value': fb['value'],
                'original_wording': fb['wording'],
                'simplified_wording': fb['wording'],
                'transaction_type': fb['type'],
                'raw_data': {'fake': True, 'scenario': f'S0{8+i}'},
            }
        )
        print(f'  Bank tx: {fb["value"]:+} EUR "{fb["wording"]}" {fb["date"]}')


def seed_mollie():
    """Create Mollie payments matching existing email transactions."""
    from mollie_provider.models import MollieConnection
    conn = MollieConnection.objects.filter(user_id=USER_ID, is_active=True).first()
    if not conn:
        print('  SKIP: not connected')
        return

    import httpx
    headers = {'Authorization': f'Bearer {conn.api_key}', 'Content-Type': 'application/json'}

    # S07: Fnac 279.99 EUR (matches email)
    # Plus some others matching email data
    payments = [
        {'amount': '279.99', 'desc': 'Fnac Order #F-001 - Ecouteurs Sony'},
        {'amount': '139.95', 'desc': 'Zalando Order #Z-042 - Nike Air Max'},
        {'amount': '87.40', 'desc': 'Leroy Merlin - Peinture + outils'},
        {'amount': '32.80', 'desc': 'Picard - Surgelés'},
        {'amount': '9.90', 'desc': 'Monthly SaaS subscription'},
    ]

    for p in payments:
        try:
            resp = httpx.post('https://api.mollie.com/v2/payments', headers=headers, json={
                'amount': {'currency': 'EUR', 'value': p['amount']},
                'description': p['desc'],
                'redirectUrl': 'https://novaledger.com/redirect',
            })
            resp.raise_for_status()
            data = resp.json()
            print(f'  Payment {p["amount"]} EUR "{p["desc"]}" → {data.get("status")}')
        except Exception as e:
            print(f'  ERROR: {e}')

    # Sync
    from mollie_provider.services.mollie_sync import sync_mollie_data
    user = CustomUser.objects.get(pk=USER_ID)
    result = sync_mollie_data(user)
    print(f'  Synced: {result}')


def seed_paypal():
    """PayPal sandbox requires browser for order capture. Just sync existing."""
    from paypal_provider.models import PayPalConnection
    conn = PayPalConnection.objects.filter(user_id=USER_ID, is_active=True).first()
    if not conn:
        print('  SKIP: not connected')
        return

    print('  PayPal sandbox needs browser to capture orders.')
    print('  Go to sandbox.paypal.com to create test transactions.')

    from paypal_provider.services.paypal_sync import sync_paypal_data
    user = CustomUser.objects.get(pk=USER_ID)
    result = sync_paypal_data(user)
    print(f'  Synced: {result}')


if __name__ == '__main__':
    print('=== Nova Ledger — Seed Test Data ===')
    print(f'User ID: {USER_ID}')
    print()

    print('[1/4] Stripe charges (matching email data)...')
    seed_stripe()
    print()

    print('[2/4] Stripe bank transactions (payouts/refunds)...')
    seed_stripe_bank_txs()
    print()

    print('[3/4] Mollie payments (matching email data)...')
    seed_mollie()
    print()

    print('[4/4] PayPal sync...')
    seed_paypal()
    print()

    print('Done! Check the front-end Providers tab + Bank tab.')
    print('Run correlation: POST /api/banking/correlate/')
