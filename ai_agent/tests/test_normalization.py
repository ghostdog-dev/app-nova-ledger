from django.test import TestCase
from ai_agent.services.normalization import normalize_vendor


class NormalizeVendorTest(TestCase):
    """Test the unified vendor normalization pipeline."""

    def test_strip_bank_prefixes(self):
        self.assertEqual(normalize_vendor('CB*AMAZON PARIS'), 'amazon')
        self.assertEqual(normalize_vendor('PRLV NETFLIX'), 'netflix')
        self.assertEqual(normalize_vendor('VIR STRIPE'), 'stripe')
        self.assertEqual(normalize_vendor('CARTE UBER'), 'uber')

    def test_strip_corporate_suffixes(self):
        self.assertEqual(normalize_vendor('Amazon Inc.'), 'amazon')
        self.assertEqual(normalize_vendor('OVH SAS'), 'ovh')
        self.assertEqual(normalize_vendor('Stripe Ltd'), 'stripe')
        self.assertEqual(normalize_vendor('Google LLC'), 'google')
        self.assertEqual(normalize_vendor('SAP GMBH'), 'sap')
        self.assertEqual(normalize_vendor('Apple Corp.'), 'apple')

    def test_strip_city_and_trailing_numbers(self):
        self.assertEqual(normalize_vendor('AMAZON PARIS 02'), 'amazon')
        self.assertEqual(normalize_vendor('UBER EATS LYON 69003'), 'uber eats')
        self.assertEqual(normalize_vendor('CARREFOUR MARKET NANTES'), 'carrefour market')

    def test_collapse_whitespace(self):
        self.assertEqual(normalize_vendor('  UBER   EATS  '), 'uber eats')

    def test_empty_and_none(self):
        self.assertEqual(normalize_vendor(''), '')
        self.assertEqual(normalize_vendor(None), '')

    def test_already_clean(self):
        self.assertEqual(normalize_vendor('netflix'), 'netflix')
        self.assertEqual(normalize_vendor('Spotify'), 'spotify')

    def test_fuzzy_match(self):
        from ai_agent.services.normalization import vendors_match
        self.assertTrue(vendors_match('amazon', 'amazon prime'))
        self.assertTrue(vendors_match('uber eats', 'uber'))
        self.assertFalse(vendors_match('netflix', 'spotify'))
        self.assertTrue(vendors_match('google cloud', 'google'))

    def test_real_world_bank_labels(self):
        self.assertEqual(normalize_vendor('CB AMAZON.FR MARKETPLACE'), 'amazon.fr marketplace')
        self.assertEqual(normalize_vendor('PRLV SEPA OVH SAS'), 'ovh')
        self.assertEqual(normalize_vendor('VIR INST MOLLIE'), 'mollie')
