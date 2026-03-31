from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Correlation, Execution
from core.serializers import CorrelationSerializer, CorrelationUpdateSerializer


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def correlation_list_view(request):
    execution_id = request.query_params.get('execution')
    if not execution_id:
        return Response(
            {'detail': 'Query parameter "execution" is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        execution = Execution.objects.get(
            public_id=execution_id,
            company__members__user=request.user,
            company__members__is_active=True,
        )
    except Execution.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    correlations = execution.correlations.prefetch_related('anomalies').all()
    serializer = CorrelationSerializer(correlations, many=True)
    return Response({'count': correlations.count(), 'results': serializer.data})


@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def correlation_detail_view(request, correlation_pk):
    try:
        correlation = Correlation.objects.get(
            public_id=correlation_pk,
            execution__company__members__user=request.user,
            execution__company__members__is_active=True,
        )
    except Correlation.DoesNotExist:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    serializer = CorrelationUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)

    for field, value in serializer.validated_data.items():
        setattr(correlation, field, value)
    correlation.save()

    return Response(CorrelationSerializer(correlation).data)
