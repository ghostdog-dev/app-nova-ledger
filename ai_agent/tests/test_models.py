from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from ai_agent.models import UnifiedTransaction, TransactionCluster, BankFileImport

User = get_user_model()


class UnifiedTransactionModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test@example.com', password='testpass123'
        )

    def test_create_minimal(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='stripe',
            source_id='ch_abc123',
            direction='inflow',
            category='revenue',
            amount=Decimal('50.00'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='Acme Corp',
        )
        self.assertEqual(ut.vendor_name_normalized, 'acme')
        self.assertEqual(ut.direction, 'inflow')
        self.assertIsNotNone(ut.public_id)

    def test_vendor_name_normalized_auto(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='bank_api',
            source_id='tx_123',
            direction='outflow',
            category='expense_service',
            amount=Decimal('29.99'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='CB*NETFLIX INC PARIS 02',
        )
        self.assertEqual(ut.vendor_name_normalized, 'netflix')

    def test_completeness_complete(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='email',
            source_id='email_42',
            direction='outflow',
            category='expense_goods',
            amount=Decimal('100.00'),
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='Amazon',
        )
        self.assertEqual(ut.completeness, 'complete')

    def test_completeness_partial_no_amount(self):
        ut = UnifiedTransaction.objects.create(
            user=self.user,
            source_type='email',
            source_id='email_43',
            direction='outflow',
            category='expense_shipping',
            currency='EUR',
            transaction_date=date(2026, 3, 15),
            vendor_name='UPS',
        )
        self.assertEqual(ut.completeness, 'partial')

    def test_unique_source(self):
        """Same source_type + source_id + user should not create duplicates."""
        UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_dup',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Test',
        )
        with self.assertRaises(Exception):
            UnifiedTransaction.objects.create(
                user=self.user, source_type='stripe', source_id='ch_dup',
                direction='inflow', category='revenue',
                amount=Decimal('50.00'), currency='EUR',
                transaction_date=date(2026, 3, 15), vendor_name='Test',
            )


class TransactionClusterModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test2@example.com', password='testpass123'
        )

    def test_create_cluster_with_transactions(self):
        cluster = TransactionCluster.objects.create(
            user=self.user,
            label='Vente produit X',
            cluster_type='sale',
        )
        ut1 = UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_1',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Client A',
            cluster=cluster,
        )
        ut2 = UnifiedTransaction.objects.create(
            user=self.user, source_type='bank_api', source_id='bt_1',
            direction='inflow', category='revenue',
            amount=Decimal('50.00'), currency='EUR',
            transaction_date=date(2026, 3, 17), vendor_name='STRIPE PAYOUT',
            cluster=cluster,
        )
        self.assertEqual(cluster.transactions.count(), 2)

    def test_recalculate_metrics(self):
        cluster = TransactionCluster.objects.create(
            user=self.user, label='Test', cluster_type='sale',
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='stripe', source_id='ch_m1',
            direction='inflow', category='revenue',
            amount=Decimal('100.00'), currency='EUR',
            transaction_date=date(2026, 3, 15), vendor_name='Client',
            cluster=cluster,
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='email', source_id='em_m1',
            direction='outflow', category='purchase_cost',
            amount=Decimal('40.00'), currency='EUR',
            transaction_date=date(2026, 3, 10), vendor_name='Fournisseur',
            cluster=cluster,
        )
        UnifiedTransaction.objects.create(
            user=self.user, source_type='email', source_id='em_m2',
            direction='outflow', category='expense_shipping',
            amount=Decimal('8.50'), currency='EUR',
            transaction_date=date(2026, 3, 12), vendor_name='UPS',
            cluster=cluster,
        )
        cluster.recalculate_metrics()
        self.assertEqual(cluster.total_revenue, Decimal('100.00'))
        self.assertEqual(cluster.total_cost, Decimal('48.50'))
        self.assertEqual(cluster.margin, Decimal('51.50'))


class BankFileImportModelTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            email='test3@example.com', password='testpass123'
        )

    def test_create_import(self):
        imp = BankFileImport.objects.create(
            user=self.user,
            file_type='csv',
            bank_name='BNP Paribas',
            account_identifier='FR76 1234 5678 9012 3456 7890 123',
            status='pending',
        )
        self.assertEqual(imp.status, 'pending')
        self.assertEqual(imp.rows_imported, 0)
