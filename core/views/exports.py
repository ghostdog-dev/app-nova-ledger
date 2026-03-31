from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, Execution, ExportFile
from core.serializers import ExportFileSerializer


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def create_export_view(request, company_pk, execution_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        execution = company.executions.get(public_id=execution_pk)
    except Execution.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    file_format = request.data.get('format')
    valid_formats = [choice[0] for choice in ExportFile.FORMAT_CHOICES]
    if file_format not in valid_formats:
        return Response(
            {'detail': f'Invalid format. Choose from: {", ".join(valid_formats)}'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    export_file = ExportFile.objects.create(
        execution=execution,
        format=file_format,
        status='ready',
        original_filename=f'export_{execution.public_id}.{file_format}',
    )

    return Response(
        ExportFileSerializer(export_file).data,
        status=status.HTTP_201_CREATED,
    )


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def export_detail_view(request, export_pk):
    try:
        export_file = ExportFile.objects.get(
            public_id=export_pk,
            execution__company__members__user=request.user,
            execution__company__members__is_active=True,
        )
    except ExportFile.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    return Response(ExportFileSerializer(export_file).data)
