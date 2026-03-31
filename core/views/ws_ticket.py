import secrets

from django.core.cache import cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response


@api_view(['POST'])
@permission_classes([IsAuthenticated])
def ws_ticket_view(request):
    ticket = secrets.token_urlsafe(32)
    cache.set(f'ws_ticket:{ticket}', request.user.pk, timeout=30)
    return Response({'ticket': ticket})
