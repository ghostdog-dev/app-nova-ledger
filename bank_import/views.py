import logging

from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import BankFileImport, ImportedTransaction
from .serializers import BankFileImportSerializer, ImportedTransactionSerializer
from .services.file_parser import compute_fingerprint, parse_bank_file

logger = logging.getLogger(__name__)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


class BankFileUploadView(APIView):
    """Upload and parse a bank file (CSV, XLS, XLSX, OFX, QIF, CFONB)."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if file_obj.size > MAX_FILE_SIZE:
            return Response(
                {'error': f'File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_bytes = file_obj.read()
        filename = file_obj.name or 'unknown'

        try:
            result = parse_bank_file(raw_bytes, filename)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Failed to parse bank file: %s', filename)
            return Response(
                {'error': 'Failed to parse file. Check the format and try again.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        bank_name = request.data.get('bank_name', result.get('bank_name', ''))

        # Create import record
        file_import = BankFileImport.objects.create(
            user=request.user,
            original_filename=filename,
            file_format=result['format'],
            file_size=len(raw_bytes),
            encoding=result.get('encoding', ''),
            separator=result.get('separator', ''),
            column_mapping=result.get('column_mapping', {}),
            bank_name=bank_name,
            account_id=result.get('account_id', ''),
            raw_preview=result.get('preview', [])[:5],
        )

        # Import transactions with dedup
        created = 0
        skipped = 0

        for txn in result['transactions']:
            fp = compute_fingerprint(request.user.id, txn)

            if ImportedTransaction.objects.filter(fingerprint=fp).exists():
                skipped += 1
                continue

            ImportedTransaction.objects.create(
                user=request.user,
                file_import=file_import,
                date=txn['date'],
                amount=txn['amount'],
                currency=txn.get('currency', 'EUR'),
                description=txn.get('description', ''),
                value_date=txn.get('value_date'),
                reference=txn.get('reference', ''),
                counterparty=txn.get('counterparty', ''),
                category=txn.get('category', ''),
                balance_after=txn.get('balance_after'),
                transaction_type=txn.get('transaction_type', ''),
                fingerprint=fp,
                raw_data=txn.get('raw_data', {}),
            )
            created += 1

        file_import.transactions_count = created
        file_import.duplicates_skipped = skipped
        file_import.save(update_fields=['transactions_count', 'duplicates_skipped'])

        logger.info(
            'Bank file imported for %s: %s — %d created, %d duplicates skipped',
            request.user.email, filename, created, skipped,
        )

        return Response({
            'import_id': file_import.id,
            'filename': filename,
            'format': result['format'],
            'encoding': result.get('encoding', ''),
            'separator': result.get('separator', ''),
            'column_mapping': result.get('column_mapping', {}),
            'transactions_created': created,
            'duplicates_skipped': skipped,
            'headers_detected': result.get('headers', []),
        })


class BankFilePreviewView(APIView):
    """Preview a bank file without importing (dry run)."""
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request):
        file_obj = request.FILES.get('file')
        if not file_obj:
            return Response({'error': 'No file provided'}, status=status.HTTP_400_BAD_REQUEST)

        if file_obj.size > MAX_FILE_SIZE:
            return Response(
                {'error': f'File too large (max {MAX_FILE_SIZE // 1024 // 1024} MB)'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        raw_bytes = file_obj.read()
        filename = file_obj.name or 'unknown'

        try:
            result = parse_bank_file(raw_bytes, filename)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception('Failed to preview bank file: %s', filename)
            return Response(
                {'error': 'Failed to parse file.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Return preview without saving
        preview_txns = []
        for txn in result['transactions'][:20]:
            preview_txns.append({
                'date': str(txn['date']),
                'amount': str(txn['amount']),
                'currency': txn.get('currency', 'EUR'),
                'description': txn.get('description', ''),
                'counterparty': txn.get('counterparty', ''),
                'reference': txn.get('reference', ''),
                'category': txn.get('category', ''),
                'balance_after': str(txn['balance_after']) if txn.get('balance_after') else None,
            })

        return Response({
            'filename': filename,
            'format': result['format'],
            'encoding': result.get('encoding', ''),
            'separator': result.get('separator', ''),
            'headers_detected': result.get('headers', []),
            'column_mapping': result.get('column_mapping', {}),
            'total_transactions': len(result['transactions']),
            'preview': preview_txns,
            'raw_preview': result.get('preview', [])[:5],
        })


class BankImportListView(APIView):
    """List all file imports for the current user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        imports = BankFileImport.objects.filter(user=request.user)
        serializer = BankFileImportSerializer(imports[:100], many=True)
        return Response(serializer.data)


class ImportedTransactionsView(APIView):
    """List imported transactions with optional filtering."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        qs = ImportedTransaction.objects.filter(user=request.user)

        import_id = request.query_params.get('import_id')
        if import_id:
            qs = qs.filter(file_import_id=import_id)

        date_from = request.query_params.get('date_from')
        if date_from:
            qs = qs.filter(date__gte=date_from)

        date_to = request.query_params.get('date_to')
        if date_to:
            qs = qs.filter(date__lte=date_to)

        serializer = ImportedTransactionSerializer(qs[:500], many=True)
        return Response(serializer.data)


class BankImportDeleteView(APIView):
    """Delete an import and all its transactions."""
    permission_classes = [IsAuthenticated]

    def delete(self, request, import_id):
        try:
            file_import = BankFileImport.objects.get(id=import_id, user=request.user)
        except BankFileImport.DoesNotExist:
            return Response({'error': 'Import not found'}, status=status.HTTP_404_NOT_FOUND)

        count = file_import.transactions.count()
        file_import.delete()  # cascade deletes transactions

        return Response({'deleted': True, 'transactions_deleted': count})
