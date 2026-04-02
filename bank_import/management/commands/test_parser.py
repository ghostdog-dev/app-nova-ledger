"""
Management command to test bank file parsing on all sample files.

Usage:
    python manage.py test_parser
    python manage.py test_parser --file bnp_releve.csv
    python manage.py test_parser --verbose
"""

import os
import sys
import traceback
from pathlib import Path

from django.core.management.base import BaseCommand

from bank_import.services.file_parser import parse_bank_file


TEST_FILES_DIR = Path(__file__).resolve().parent.parent.parent / 'test_files'


class Command(BaseCommand):
    help = 'Test the bank file parser against all sample files in bank_import/test_files/'

    def add_arguments(self, parser):
        parser.add_argument(
            '--file',
            type=str,
            default=None,
            help='Test a single file by name (e.g. bnp_releve.csv)',
        )
        parser.add_argument(
            '--verbose',
            action='store_true',
            help='Show all transactions, not just the first 3',
        )

    def handle(self, *args, **options):
        single_file = options.get('file')
        verbose = options.get('verbose', False)

        if not TEST_FILES_DIR.exists():
            self.stderr.write(self.style.ERROR(
                f'Test files directory not found: {TEST_FILES_DIR}'
            ))
            return

        # Collect test files
        if single_file:
            files = [TEST_FILES_DIR / single_file]
            if not files[0].exists():
                self.stderr.write(self.style.ERROR(f'File not found: {files[0]}'))
                return
        else:
            files = sorted(
                f for f in TEST_FILES_DIR.iterdir()
                if f.is_file() and not f.name.startswith('.')
            )

        if not files:
            self.stderr.write(self.style.WARNING('No test files found.'))
            return

        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n{"=" * 70}'
            f'\n  Bank File Parser Test Suite'
            f'\n  Directory: {TEST_FILES_DIR}'
            f'\n  Files: {len(files)}'
            f'\n{"=" * 70}\n'
        ))

        success_count = 0
        fail_count = 0
        results = []

        for filepath in files:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f'\n{"─" * 70}'
                f'\n  File: {filepath.name}'
                f'\n{"─" * 70}'
            ))

            try:
                raw_bytes = filepath.read_bytes()
                file_size = len(raw_bytes)

                result = parse_bank_file(raw_bytes, filepath.name)

                txn_count = len(result.get('transactions', []))
                success_count += 1

                # Print result summary
                self.stdout.write(f'  Status:          {self.style.SUCCESS("OK")}')
                self.stdout.write(f'  File size:       {file_size:,} bytes')
                self.stdout.write(f'  Format:          {result["format"]}')
                self.stdout.write(f'  Encoding:        {result.get("encoding", "n/a")}')

                sep = result.get('separator', '')
                if sep:
                    sep_display = repr(sep)
                else:
                    sep_display = 'n/a'
                self.stdout.write(f'  Separator:       {sep_display}')

                headers = result.get('headers', [])
                if headers:
                    self.stdout.write(f'  Headers:         {headers}')

                mapping = result.get('column_mapping', {})
                self.stdout.write(f'  Column mapping:  {mapping}')
                self.stdout.write(f'  Transactions:    {self.style.SUCCESS(str(txn_count))}')

                # Show transactions
                transactions = result['transactions']
                show_count = len(transactions) if verbose else min(3, len(transactions))

                if show_count > 0:
                    self.stdout.write(f'\n  {"First " + str(show_count) + " transactions:" if not verbose else "All transactions:"}')
                    for i, txn in enumerate(transactions[:show_count]):
                        amount = txn['amount']
                        if amount >= 0:
                            amount_str = self.style.SUCCESS(f'+{amount}')
                        else:
                            amount_str = self.style.ERROR(str(amount))

                        desc = txn.get('description', '')
                        if len(desc) > 60:
                            desc = desc[:57] + '...'

                        self.stdout.write(
                            f'    {i + 1:3d}. {txn["date"]}  {amount_str:>30s}  {desc}'
                        )

                        # Show extra fields if present
                        extras = []
                        if txn.get('counterparty'):
                            extras.append(f'counterparty={txn["counterparty"]}')
                        if txn.get('category'):
                            extras.append(f'category={txn["category"]}')
                        if txn.get('reference'):
                            extras.append(f'ref={txn["reference"]}')
                        if txn.get('balance_after') is not None:
                            extras.append(f'balance={txn["balance_after"]}')
                        if extras:
                            self.stdout.write(f'         {", ".join(extras)}')

                results.append({
                    'file': filepath.name,
                    'status': 'OK',
                    'format': result['format'],
                    'transactions': txn_count,
                })

            except Exception as e:
                fail_count += 1
                self.stdout.write(f'  Status:          {self.style.ERROR("FAILED")}')
                self.stdout.write(f'  Error:           {self.style.ERROR(str(e))}')
                if verbose:
                    self.stdout.write(f'\n  Traceback:')
                    self.stdout.write(traceback.format_exc())

                results.append({
                    'file': filepath.name,
                    'status': 'FAILED',
                    'error': str(e),
                })

        # Summary
        total = success_count + fail_count
        self.stdout.write(self.style.MIGRATE_HEADING(
            f'\n{"=" * 70}'
            f'\n  SUMMARY'
            f'\n{"=" * 70}'
        ))

        for r in results:
            status = self.style.SUCCESS('OK') if r['status'] == 'OK' else self.style.ERROR('FAIL')
            if r['status'] == 'OK':
                self.stdout.write(
                    f'  {status}  {r["file"]:<30s}  format={r["format"]:<6s}  '
                    f'transactions={r["transactions"]}'
                )
            else:
                self.stdout.write(
                    f'  {status}  {r["file"]:<30s}  error={r["error"][:50]}'
                )

        self.stdout.write(f'\n  Result: {success_count}/{total} files parsed successfully')

        if fail_count == 0:
            self.stdout.write(self.style.SUCCESS(f'\n  All {total} test files passed!\n'))
        else:
            self.stdout.write(self.style.ERROR(
                f'\n  {fail_count} file(s) failed. Run with --verbose for details.\n'
            ))
            sys.exit(1)
