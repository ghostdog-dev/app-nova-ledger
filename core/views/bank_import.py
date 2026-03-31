import logging

from django.db import IntegrityError
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from ai_agent.models import BankFileImport, UnifiedTransaction
from ai_agent.services.normalizers.bank_import import BankImportNormalizer
from ai_agent.services.parsers.csv_parser import CSVBankParser

logger = logging.getLogger(__name__)


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
        else:
            return Response(
                {'error': f'Unsupported file type: {filename}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Create import record
        bank_import = BankFileImport.objects.create(
            user=request.user,
            file=file,
            file_type=file_type,
            status='parsing',
        )

        # Parse
        file_content = file.read()

        if file_type == 'csv':
            parser = CSVBankParser()
            result = parser.parse(file_content, filename=file.name)
        else:
            bank_import.status = 'failed'
            bank_import.error_message = f'{file_type} parser not yet implemented'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': f'{file_type} parser not yet implemented',
            }, status=status.HTTP_501_NOT_IMPLEMENTED)

        if not result or not result.transactions:
            bank_import.status = 'failed'
            bank_import.error_message = 'Could not parse any transactions from file'
            bank_import.save()
            return Response({
                'status': 'error',
                'error': 'Could not parse file. Check the format.',
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

        return Response({
            'status': 'imported',
            'import_id': bank_import.id,
            'bank_name': result.bank_name,
            'rows_total': len(result.transactions),
            'rows_imported': imported,
            'rows_skipped': skipped,
            'date_range': [str(d) for d in result.date_range] if result.date_range else None,
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
                'file_type': imp.file_type,
                'bank_name': imp.bank_name,
                'status': imp.status,
                'rows_total': imp.rows_total,
                'rows_imported': imp.rows_imported,
                'rows_skipped': imp.rows_skipped,
                'date_from': str(imp.date_from) if imp.date_from else None,
                'date_to': str(imp.date_to) if imp.date_to else None,
                'uploaded_at': imp.uploaded_at.isoformat(),
            }
            for imp in imports
        ]
        return Response(data)
