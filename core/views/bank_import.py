import logging
from decimal import Decimal

from django.db import IntegrityError
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import BankFileImport, UnifiedTransaction
from ai_agent.services.normalizers.bank_import import BankImportNormalizer
from ai_agent.services.parsers.csv_parser import CSVBankParser
from core.models import Company, ServiceConnection

logger = logging.getLogger(__name__)


def _get_or_create_bank_connection(user, company_pk, bank_name, file_type):
    """Create a ServiceConnection for the bank import so it shows in Connections page."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None

    label = bank_name or f'Import {file_type.upper()}'

    # Reuse existing connection if same provider
    conn = ServiceConnection.objects.filter(
        company=company, provider_name='bank_import', service_type='banking',
    ).first()

    if conn:
        conn.status = 'active'
        conn.last_sync = timezone.now()
        conn.save()
        return conn

    return ServiceConnection.objects.create(
        company=company,
        service_type='banking',
        provider_name='bank_import',
        auth_type='file_upload',
        status='active',
        last_sync=timezone.now(),
        credentials={'bank_name': label},
    )


class BankFileUploadView(APIView):
    """POST /api/v1/companies/{company_pk}/bank-import/upload/"""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, company_pk):
        file = request.FILES.get('file')
        if not file:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        # Detect file type
        filename = file.name.lower()
        if filename.endswith('.csv'):
            file_type = 'csv'
        elif filename.endswith(('.ofx', '.qfx')):
            file_type = 'ofx'
        elif filename.endswith('.xml'):
            file_type = 'camt053'
        elif filename.endswith('.pdf'):
            file_type = 'pdf'
        else:
            return Response(
                {'error': f'Format non supporté: {filename}. Formats acceptés: CSV, OFX, QFX, XML, PDF'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Read content before Django consumes the stream
        file_content = file.read()
        file.seek(0)

        # Create import record
        bank_import = BankFileImport.objects.create(
            user=request.user,
            file=file,
            file_type=file_type,
            status='parsing',
        )

        if file_type == 'csv':
            parser = CSVBankParser()
            result = parser.parse(file_content, filename=file.name)
        elif file_type == 'pdf':
            # Save immediately, parse in background thread
            bank_import.status = 'parsing'
            bank_import.parser_used = 'pdf_claude_haiku'
            bank_import.save()
            _get_or_create_bank_connection(request.user, company_pk, 'Import PDF', 'pdf')

            # Launch background parsing
            import threading
            user = request.user
            import_id = bank_import.id
            company = company_pk

            def _parse_pdf_background():
                import django
                django.db.connections.close_all()
                from ai_agent.services.parsers.pdf_parser import parse_pdf_bank_statement
                from ai_agent.models import UnifiedTransaction as UT
                from datetime import date as date_cls

                imp = BankFileImport.objects.get(id=import_id)
                try:
                    pdf_result = parse_pdf_bank_statement(file_content)
                    if not pdf_result or not pdf_result.get('transactions'):
                        imp.status = 'failed'
                        imp.error_message = 'IA n\'a pas pu extraire de transactions'
                        imp.save()
                        return

                    imp.bank_name = pdf_result.get('bank_name', '')
                    imp.rows_total = len(pdf_result['transactions'])
                    if pdf_result.get('account_id'):
                        imp.account_identifier = pdf_result['account_id']

                    imported = 0
                    skipped = 0
                    dates = []
                    for tx in pdf_result['transactions']:
                        try:
                            tx_date = date_cls.fromisoformat(tx['date']) if tx.get('date') else None
                            amount = Decimal(str(tx['amount'])) if tx.get('amount') is not None else None
                            direction = 'outflow' if amount and amount < 0 else 'inflow'
                            abs_amount = abs(amount) if amount else amount

                            UT.objects.create(
                                user=user,
                                source_type='bank_import',
                                source_id=f'bank_{tx.get("date", "")}_{tx.get("label", "")[:40]}_{tx.get("amount", "")}',
                                direction=direction,
                                category='other',
                                amount=abs_amount,
                                currency=tx.get('currency', 'EUR').upper(),
                                transaction_date=tx_date,
                                vendor_name=tx.get('label', ''),
                                description=tx.get('label', ''),
                                confidence=0.85,
                            )
                            imported += 1
                            if tx_date:
                                dates.append(tx_date)
                        except IntegrityError:
                            skipped += 1
                        except Exception as e:
                            logger.error(f'[PDF bg] Error: {e}')
                            skipped += 1

                    imp.rows_imported = imported
                    imp.rows_skipped = skipped
                    imp.status = 'parsed'
                    if dates:
                        imp.date_from = min(dates)
                        imp.date_to = max(dates)
                    imp.save()

                    # Update connection status
                    _get_or_create_bank_connection(user, company, imp.bank_name or 'Import PDF', 'pdf')
                    logger.info(f'[PDF bg] Done: {imported} imported, {skipped} skipped')

                except Exception as e:
                    logger.error(f'[PDF bg] Failed: {e}')
                    imp.status = 'failed'
                    imp.error_message = str(e)[:500]
                    imp.save()

            threading.Thread(target=_parse_pdf_background, daemon=True).start()

            return Response({
                'status': 'processing',
                'importId': bank_import.id,
                'message': 'PDF reçu, traitement en cours par l\'IA...',
            })
        else:
            bank_import.status = 'failed'
            bank_import.error_message = f'Parser {file_type} pas encore disponible'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': f'Parser {file_type} pas encore disponible. Utilisez CSV pour le moment.',
            }, status=status.HTTP_501_NOT_IMPLEMENTED)

        if not result or not result.transactions:
            bank_import.status = 'failed'
            bank_import.error_message = 'Could not parse any transactions from file'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': 'Impossible de parser le fichier. Vérifiez le format.',
                'warnings': result.warnings if result else [],
            }, status=status.HTTP_400_BAD_REQUEST)

        bank_import.bank_name = result.bank_name or ''
        bank_import.rows_total = len(result.transactions)
        if result.date_range:
            bank_import.date_from = result.date_range[0]
            bank_import.date_to = result.date_range[1]

        # Import transactions
        normalizer = BankImportNormalizer()
        imported = 0
        skipped = 0

        for row in result.transactions:
            try:
                ut = normalizer.normalize(request.user, row, bank_import.id)
                ut.save()
                imported += 1
            except IntegrityError:
                skipped += 1
            except Exception as e:
                logger.error(f'[BankImport] Error importing row: {e}')
                skipped += 1

        bank_import.rows_imported = imported
        bank_import.rows_skipped = skipped
        bank_import.status = 'parsed'
        bank_import.parser_used = f'csv_{result.bank_name}' if result.bank_name else 'csv_heuristic'
        bank_import.save()

        # Create/update ServiceConnection so it appears in Connections page
        _get_or_create_bank_connection(
            request.user, company_pk,
            result.bank_name or 'Import CSV', file_type,
        )

        return Response({
            'status': 'imported',
            'importId': bank_import.id,
            'bankName': result.bank_name,
            'rowsTotal': len(result.transactions),
            'rowsImported': imported,
            'rowsSkipped': skipped,
            'dateRange': [str(d) for d in result.date_range] if result.date_range else None,
            'warnings': result.warnings[:10],
        })


class BankImportListView(APIView):
    """GET /api/v1/companies/{company_pk}/bank-import/"""
    permission_classes = [IsAuthenticated]

    def get(self, request, company_pk):
        imports = BankFileImport.objects.filter(user=request.user).order_by('-uploaded_at')[:20]
        data = [
            {
                'id': imp.id,
                'fileType': imp.file_type,
                'bankName': imp.bank_name,
                'status': imp.status,
                'rowsTotal': imp.rows_total,
                'rowsImported': imp.rows_imported,
                'rowsSkipped': imp.rows_skipped,
                'dateFrom': str(imp.date_from) if imp.date_from else None,
                'dateTo': str(imp.date_to) if imp.date_to else None,
                'uploadedAt': imp.uploaded_at.isoformat(),
            }
            for imp in imports
        ]
        return Response(data)
