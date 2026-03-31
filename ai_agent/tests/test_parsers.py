from datetime import date
from decimal import Decimal

from django.test import TestCase

from ai_agent.services.parsers.csv_parser import CSVBankParser, ParseResult


class CSVBankParserTest(TestCase):

    def test_parse_bnp_format(self):
        content = (
            '"Date opération";"Libellé";"Débit";"Crédit"\n'
            '"15/03/2026";"CB AMAZON PARIS 02";"-49.99";""\n'
            '"16/03/2026";"VIR STRIPE PAYOUT";"";"+500.00"\n'
        ).encode('latin-1')

        parser = CSVBankParser()
        result = parser.parse(content, filename='export_bnp.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)

        tx1 = result.transactions[0]
        self.assertEqual(tx1.date, date(2026, 3, 15))
        self.assertEqual(tx1.amount, Decimal('-49.99'))
        self.assertEqual(tx1.label, 'CB AMAZON PARIS 02')

        tx2 = result.transactions[1]
        self.assertEqual(tx2.amount, Decimal('500.00'))

    def test_parse_revolut_format(self):
        content = (
            'Type,Started Date,Completed Date,Description,Amount,Currency\n'
            'CARD_PAYMENT,2026-03-15 10:00:00,2026-03-15 10:00:00,Amazon,-25.00,EUR\n'
            'TOPUP,2026-03-16 12:00:00,2026-03-16 12:00:00,Top-up,100.00,EUR\n'
        ).encode('utf-8')

        parser = CSVBankParser()
        result = parser.parse(content, filename='revolut.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)
        self.assertEqual(result.transactions[0].amount, Decimal('-25.00'))
        self.assertEqual(result.transactions[0].currency, 'EUR')

    def test_parse_generic_csv(self):
        content = (
            'Date;Description;Montant\n'
            '15/03/2026;Achat Amazon;-35.50\n'
            '16/03/2026;Salaire;+2500.00\n'
        ).encode('utf-8')

        parser = CSVBankParser()
        result = parser.parse(content, filename='banque.csv')
        self.assertIsNotNone(result)
        self.assertEqual(len(result.transactions), 2)

    def test_detect_encoding(self):
        parser = CSVBankParser()
        # Latin-1 with accented chars
        content = '"Libellé";"Crédit"'.encode('latin-1')
        encoding = parser._detect_encoding(content)
        self.assertIn(encoding.lower(), ['latin-1', 'iso-8859-1', 'windows-1252', 'latin1', 'cp1250'])

    def test_empty_file(self):
        parser = CSVBankParser()
        result = parser.parse(b'', filename='empty.csv')
        self.assertIsNone(result)
