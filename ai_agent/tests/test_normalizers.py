from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_agent.models import UnifiedTransaction
from ai_agent.services.normalizers.base import BaseNormalizer
from ai_agent.services.normalizers.stripe import StripeNormalizer
from ai_agent.services.normalizers.mollie import MollieNormalizer
from ai_agent.services.normalizers.paypal import PayPalNormalizer
from ai_agent.services.normalizers.bank_api import BankAPINormalizer
from ai_agent.services.normalizers.email import EmailNormalizer

User = get_user_model()


class StripeNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='s@test.com', password='test123')
        self.normalizer = StripeNormalizer()

    def test_normalize_charge(self):
        charge = MagicMock()
        charge.pk = 1
        charge.stripe_id = 'ch_abc123'
        charge.amount = 5000  # cents
        charge.currency = 'eur'
        charge.created_at_stripe = '2026-03-15T10:00:00Z'
        charge.description = 'Payment for order #123'
        charge.statement_descriptor = 'ACME CORP'
        charge.status = 'succeeded'
        charge.payment_method_type = 'card'

        ut = self.normalizer.normalize_charge(self.user, charge)
        self.assertEqual(ut.source_type, 'stripe')
        self.assertEqual(ut.source_id, 'ch_abc123')
        self.assertEqual(ut.direction, 'inflow')
        self.assertEqual(ut.category, 'revenue')
        self.assertEqual(ut.amount, Decimal('50.00'))
        self.assertEqual(ut.currency, 'EUR')
        self.assertEqual(ut.vendor_name, 'ACME CORP')
        self.assertEqual(ut.transaction_date, date(2026, 3, 15))

    def test_normalize_payout(self):
        payout = MagicMock()
        payout.pk = 2
        payout.stripe_id = 'po_xyz789'
        payout.amount = 10000  # cents
        payout.currency = 'eur'
        payout.arrival_date = '2026-03-17'
        payout.status = 'paid'

        ut = self.normalizer.normalize_payout(self.user, payout)
        self.assertEqual(ut.source_type, 'stripe')
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.category, 'transfer')
        self.assertEqual(ut.amount, Decimal('100.00'))


class MollieNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='m@test.com', password='test123')
        self.normalizer = MollieNormalizer()

    def test_normalize_payment(self):
        payment = MagicMock()
        payment.pk = 1
        payment.mollie_id = 'tr_abc123'
        payment.amount = Decimal('25.50')
        payment.currency = 'EUR'
        payment.paid_at = '2026-03-15T14:30:00+00:00'
        payment.created_at_mollie = '2026-03-15T14:25:00+00:00'
        payment.description = 'Order #456'
        payment.method = 'ideal'
        payment.status = 'paid'

        ut = self.normalizer.normalize_payment(self.user, payment)
        self.assertEqual(ut.source_type, 'mollie')
        self.assertEqual(ut.amount, Decimal('25.50'))
        self.assertEqual(ut.payment_method, 'ideal')
        self.assertEqual(ut.direction, 'inflow')


class PayPalNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='p@test.com', password='test123')
        self.normalizer = PayPalNormalizer()

    def test_normalize_transaction(self):
        tx = MagicMock()
        tx.pk = 1
        tx.paypal_id = 'PAY-123'
        tx.amount = Decimal('99.99')
        tx.currency = 'USD'
        tx.initiation_date = '2026-03-15T10:00:00Z'
        tx.description = 'Invoice payment'
        tx.fee = Decimal('2.99')
        tx.status = 'S'  # success

        ut = self.normalizer.normalize_transaction(self.user, tx)
        self.assertEqual(ut.source_type, 'paypal')
        self.assertEqual(ut.amount, Decimal('99.99'))
        self.assertEqual(ut.currency, 'USD')


class BankAPINormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='b@test.com', password='test123')
        self.normalizer = BankAPINormalizer()

    def test_normalize_debit(self):
        bt = MagicMock()
        bt.pk = 10
        bt.powens_transaction_id = 12345
        bt.value = Decimal('-49.99')
        bt.date = date(2026, 3, 17)
        bt.rdate = date(2026, 3, 15)
        bt.original_wording = 'CB*AMAZON PARIS 02'
        bt.simplified_wording = 'Amazon'
        bt.transaction_type = 'card'
        bt.original_currency = ''
        bt.original_value = None
        bt.account = MagicMock()
        bt.account.currency = 'EUR'

        ut = self.normalizer.normalize(self.user, bt)
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.amount, Decimal('49.99'))  # absolute value
        self.assertEqual(ut.transaction_date, date(2026, 3, 15))  # rdate preferred
        self.assertEqual(ut.vendor_name, 'CB*AMAZON PARIS 02')

    def test_normalize_credit(self):
        bt = MagicMock()
        bt.pk = 11
        bt.powens_transaction_id = 12346
        bt.value = Decimal('500.00')
        bt.date = date(2026, 3, 20)
        bt.rdate = None
        bt.original_wording = 'VIR STRIPE PAYOUT'
        bt.simplified_wording = 'Stripe'
        bt.transaction_type = 'transfer'
        bt.original_currency = ''
        bt.original_value = None
        bt.account = MagicMock()
        bt.account.currency = 'EUR'

        ut = self.normalizer.normalize(self.user, bt)
        self.assertEqual(ut.direction, 'inflow')
        self.assertEqual(ut.amount, Decimal('500.00'))
        self.assertEqual(ut.transaction_date, date(2026, 3, 20))  # fallback to date


class EmailNormalizerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='e@test.com', password='test123')
        self.normalizer = EmailNormalizer()

    def test_normalize_invoice(self):
        tx = MagicMock()
        tx.pk = 5
        tx.type = 'invoice'
        tx.vendor_name = 'OVH SAS'
        tx.amount = Decimal('14.39')
        tx.currency = 'EUR'
        tx.transaction_date = date(2026, 3, 1)
        tx.invoice_number = 'INV-2026-001'
        tx.order_number = ''
        tx.amount_tax_excl = Decimal('11.99')
        tx.tax_amount = Decimal('2.40')
        tx.tax_rate = Decimal('20.0')
        tx.payment_method = 'debit card'
        tx.payment_reference = ''
        tx.items = [{'name': 'VPS Cloud', 'quantity': 1, 'unit_price': 11.99}]
        tx.description = 'Monthly VPS hosting'
        tx.confidence = 0.95
        tx.status = 'complete'

        ut = self.normalizer.normalize(self.user, tx)
        self.assertEqual(ut.source_type, 'email')
        self.assertEqual(ut.direction, 'outflow')
        self.assertEqual(ut.category, 'expense_service')
        self.assertEqual(ut.reference, 'INV-2026-001')
        self.assertEqual(ut.amount_tax_excl, Decimal('11.99'))
        self.assertEqual(ut.items, [{'name': 'VPS Cloud', 'quantity': 1, 'unit_price': 11.99}])
