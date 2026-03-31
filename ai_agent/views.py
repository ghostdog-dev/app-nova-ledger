import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger(__name__)


@method_decorator(csrf_exempt, name='dispatch')
class AIClassifyView(APIView):
    """POST /api/ai/classify/ — run the full AI pipeline."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ai_agent.services.pipeline import run_pipeline
        result = run_pipeline(request.user)
        return Response(result)


@method_decorator(csrf_exempt, name='dispatch')
class AICorrelateView(APIView):
    """POST /api/ai/correlate/ — run bank+provider correlation."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ai_agent.services.correlation import correlate_transactions, correlate_providers
        bank_stats = correlate_transactions(request.user)
        provider_stats = correlate_providers(request.user)
        return Response({**bank_stats, **provider_stats})


@login_required
def classify_batch_view(request):
    """Submit batch classification (async, 50% cheaper)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    from ai_agent.services.batch_pipeline import submit_batch_pipeline
    result = submit_batch_pipeline(request.user)
    status_code = 200 if 'error' not in result else 400
    return JsonResponse(result, status=status_code)


@login_required
def classify_batch_status_view(request, run_id):
    """Poll batch classification status."""
    from ai_agent.services.batch_pipeline import poll_batch_pipeline
    result = poll_batch_pipeline(run_id, request.user)
    return JsonResponse(result)


@method_decorator(csrf_exempt, name='dispatch')
class UnifiedPipelineView(APIView):
    """POST /api/ai/unified-pipeline/ — run the new unified pipeline."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from ai_agent.services.orchestrator import run_unified_pipeline
        result = run_unified_pipeline(request.user)
        return Response(result)
