from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.models import CustomUser
from core.models import Company, CompanyMember
from core.serializers import CompanyMemberSerializer, CompanySerializer

PLAN_LIMITS = {
    'free': {'executions_per_month': 5, 'connections': 3, 'members': 1},
    'plan1': {'executions_per_month': 50, 'connections': 15, 'members': 5},
    'plan2': {'executions_per_month': None, 'connections': None, 'members': None},
}

PLAN_DISPLAY = {
    'free': 'Gratuit',
    'plan1': 'Pro',
    'plan2': 'Enterprise',
}


def _get_company(user, company_pk):
    """Get company by public_id if user is an active member."""
    try:
        company = Company.objects.get(public_id=company_pk)
    except Company.DoesNotExist:
        return None
    if not company.members.filter(user=user, is_active=True).exists():
        return None
    return company


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def company_list_view(request):
    if request.method == 'GET':
        companies = Company.objects.filter(
            members__user=request.user,
            members__is_active=True,
        ).distinct()
        serializer = CompanySerializer(companies, many=True)
        return Response({'count': companies.count(), 'results': serializer.data})

    # POST
    serializer = CompanySerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    company = serializer.save(owner=request.user)
    CompanyMember.objects.create(company=company, user=request.user, role='owner')
    return Response(CompanySerializer(company).data, status=status.HTTP_201_CREATED)


@api_view(['GET', 'PATCH'])
@permission_classes([IsAuthenticated])
def company_detail_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        return Response(CompanySerializer(company).data)

    # PATCH
    serializer = CompanySerializer(company, data=request.data, partial=True)
    serializer.is_valid(raise_exception=True)
    # Only allow updating name, siret, sector
    allowed = {'name', 'siret', 'sector'}
    update_fields = set(serializer.validated_data.keys())
    disallowed = update_fields - allowed
    if disallowed:
        return Response(
            {'detail': f'Cannot update fields: {", ".join(sorted(disallowed))}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    serializer.save()
    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_plan_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    return Response({
        'plan': company.plan,
        'plan_display': PLAN_DISPLAY.get(company.plan, company.plan),
        'limits': PLAN_LIMITS.get(company.plan, {}),
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def company_usage_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    now = timezone.now()
    executions_this_month = company.executions.filter(
        created_at__year=now.year,
        created_at__month=now.month,
    ).count()

    return Response({
        'executions_this_month': executions_this_month,
        'connections': company.connections.count(),
        'members': company.members.count(),
        'limits': PLAN_LIMITS.get(company.plan, {}),
    })


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def company_members_view(request, company_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    if request.method == 'GET':
        members = company.members.select_related('user').all()
        serializer = CompanyMemberSerializer(members, many=True)
        return Response({'count': members.count(), 'results': serializer.data})

    # POST - invite member by email
    email = request.data.get('email')
    role = request.data.get('role', 'member')
    if not email:
        return Response(
            {'detail': 'Email is required.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    user, _created = CustomUser.objects.get_or_create(
        email=email,
        defaults={'first_name': '', 'last_name': ''},
    )

    if company.members.filter(user=user).exists():
        return Response(
            {'detail': 'User is already a member of this company.'},
            status=status.HTTP_400_BAD_REQUEST,
        )

    member = CompanyMember.objects.create(company=company, user=user, role=role)
    return Response(CompanyMemberSerializer(member).data, status=status.HTTP_201_CREATED)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def company_member_detail_view(request, company_pk, member_pk):
    company = _get_company(request.user, company_pk)
    if company is None:
        return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)

    try:
        member = company.members.get(pk=member_pk)
    except CompanyMember.DoesNotExist:
        return Response({'detail': 'Member not found.'}, status=status.HTTP_404_NOT_FOUND)

    member.delete()
    return Response(status=status.HTTP_204_NO_CONTENT)
