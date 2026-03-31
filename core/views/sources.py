from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from core.models import Company, CompanyMember, ServiceConnection


def _get_company(user, company_pk):
    try:
        company = Company.objects.get(public_id=company_pk)
    except (Company.DoesNotExist, ValueError):
        return None
    is_member = CompanyMember.objects.filter(company=company, user=user, is_active=True).exists()
    if is_member or company.owner == user:
        return company
    return None


def _paginate(qs, request):
    page = int(request.query_params.get('page', 1))
    page_size = int(request.query_params.get('page_size', 50))
    total_count = qs.count()
    start = (page - 1) * page_size
    items = list(qs[start:start + page_size])
    return items, {
        'total_count': total_count,
        'page': page,
        'page_size': page_size,
        'total_pages': max(1, (total_count + page_size - 1) // page_size),
    }


def _cents_to_units(val):
    """Convert cents to currency units."""
    return val / 100 if val else 0


def _response(provider, service_type, last_sync, items, pagination, columns):
    return Response({
        'provider_name': provider,
        'service_type': service_type,
        'last_sync': last_sync,
        'items': items,
        'columns': columns,
        **pagination,
    })


def _get_provider_connection(model_class, user):
    """Get a provider-specific connection (OneToOne with user)."""
    try:
        return model_class.objects.get(user=user)
    except model_class.DoesNotExist:
        return None


def _empty_response(provider, service_type, last_sync, request):
    _, pagination = _paginate(ServiceConnection.objects.none(), request)
    return _response(provider, service_type, last_sync, [], pagination, [])


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def connection_data_view(request, company_pk, connection_pk):
    company = _get_company(request.user, company_pk)
    if not company:
        return Response({'detail': 'Company not found'}, status=status.HTTP_404_NOT_FOUND)

    try:
        connection = ServiceConnection.objects.get(company=company, public_id=connection_pk)
    except (ServiceConnection.DoesNotExist, ValueError):
        return Response({'detail': 'Connection not found'}, status=status.HTTP_404_NOT_FOUND)

    provider = connection.provider_name
    service_type = connection.service_type
    last_sync = connection.last_sync.isoformat() if connection.last_sync else None
    user = request.user

    # ── Email ────────────────────────────────────────────────
    if provider in ('gmail', 'outlook'):
        return _handle_email(provider, service_type, last_sync, user, request)

    # ── Payment providers ────────────────────────────────────
    if provider == 'stripe':
        return _handle_stripe(provider, service_type, last_sync, user, request)
    if provider == 'paypal':
        return _handle_paypal(provider, service_type, last_sync, user, request)
    if provider == 'mollie':
        return _handle_mollie(provider, service_type, last_sync, user, request)
    if provider == 'fintecture':
        return _handle_fintecture(provider, service_type, last_sync, user, request)
    if provider == 'gocardless':
        return _handle_gocardless(provider, service_type, last_sync, user, request)
    if provider == 'payplug':
        return _handle_payplug(provider, service_type, last_sync, user, request)
    if provider == 'sumup':
        return _handle_sumup(provider, service_type, last_sync, user, request)
    if provider == 'qonto':
        return _handle_qonto(provider, service_type, last_sync, user, request)
    if provider == 'alma':
        return _handle_alma(provider, service_type, last_sync, user, request)

    # ── Invoicing providers ──────────────────────────────────
    if provider == 'evoliz':
        return _handle_evoliz(provider, service_type, last_sync, user, request)
    if provider == 'pennylane':
        return _handle_pennylane(provider, service_type, last_sync, user, request)
    if provider == 'vosfactures':
        return _handle_vosfactures(provider, service_type, last_sync, user, request)
    if provider == 'choruspro':
        return _handle_choruspro(provider, service_type, last_sync, user, request)

    # ── E-commerce ───────────────────────────────────────────
    if provider == 'shopify':
        return _handle_shopify(provider, service_type, last_sync, user, request)
    if provider == 'prestashop':
        return _handle_prestashop(provider, service_type, last_sync, user, request)
    if provider == 'woocommerce':
        return _handle_woocommerce(provider, service_type, last_sync, user, request)

    return _empty_response(provider, service_type, last_sync, request)


# ═══════════════════════════════════════════════════════════════
# Email
# ═══════════════════════════════════════════════════════════════

def _handle_email(provider, service_type, last_sync, user, request):
    from emails.models import Email
    provider_map = {'gmail': 'google', 'outlook': 'microsoft'}
    qs = Email.objects.filter(user=user, provider=provider_map.get(provider)).order_by('-date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': e.id, 'date': e.date.isoformat(), 'sender': e.from_address,
        'subject': e.subject, 'status': e.status,
    } for e in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'sender', 'subject', 'status'])


# ═══════════════════════════════════════════════════════════════
# Payment providers
# ═══════════════════════════════════════════════════════════════

def _handle_stripe(provider, service_type, last_sync, user, request):
    from stripe_provider.models import StripeBalanceTransaction, StripeConnection
    conn = _get_provider_connection(StripeConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = StripeBalanceTransaction.objects.filter(connection=conn).order_by('-created_at_stripe')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.created_at_stripe.isoformat() if t.created_at_stripe else '',
        'description': t.description or t.type or '', 'amount': _cents_to_units(t.amount),
        'currency': (t.currency or '').upper(), 'fee': _cents_to_units(t.fee),
        'net': _cents_to_units(t.net), 'type': t.type or '', 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'fee', 'net', 'status'])


def _handle_paypal(provider, service_type, last_sync, user, request):
    from paypal_provider.models import PayPalTransaction, PayPalConnection
    conn = _get_provider_connection(PayPalConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = PayPalTransaction.objects.filter(connection=conn).order_by('-initiation_date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.initiation_date.isoformat() if t.initiation_date else '',
        'description': t.payer_email or '', 'amount': float(t.amount) if t.amount else 0,
        'currency': (t.currency or '').upper(), 'fee': float(t.fee) if t.fee else 0,
        'net': float(t.net) if t.net else 0, 'status': t.transaction_status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'fee', 'net', 'status'])


def _handle_mollie(provider, service_type, last_sync, user, request):
    from mollie_provider.models import MolliePayment, MollieConnection
    conn = _get_provider_connection(MollieConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = MolliePayment.objects.filter(connection=conn).order_by('-created_at_mollie')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.created_at_mollie.isoformat() if t.created_at_mollie else '',
        'description': t.description or t.method or '', 'amount': float(t.amount) if t.amount else 0,
        'currency': (t.currency or '').upper(), 'method': t.method or '', 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'method', 'status'])


def _handle_fintecture(provider, service_type, last_sync, user, request):
    from fintecture_provider.models import FintecturePayment, FintectureConnection
    conn = _get_provider_connection(FintectureConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = FintecturePayment.objects.filter(connection=conn).order_by('-execution_date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.execution_date.isoformat() if t.execution_date else '',
        'description': t.communication or '', 'amount': float(t.amount) if t.amount else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_gocardless(provider, service_type, last_sync, user, request):
    from gocardless_provider.models import GoCardlessPayment, GoCardlessConnection
    conn = _get_provider_connection(GoCardlessConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = GoCardlessPayment.objects.filter(connection=conn).order_by('-charge_date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.charge_date.isoformat() if t.charge_date else '',
        'description': t.reference or '', 'amount': _cents_to_units(t.amount),
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_payplug(provider, service_type, last_sync, user, request):
    from payplug_provider.models import PayPlugPayment, PayPlugConnection
    conn = _get_provider_connection(PayPlugConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = PayPlugPayment.objects.filter(connection=conn).order_by('-created_at_payplug')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.created_at_payplug.isoformat() if t.created_at_payplug else '',
        'description': t.billing_email or '', 'amount': _cents_to_units(t.amount),
        'currency': (t.currency or '').upper(),
        'status': 'paid' if t.is_paid else ('refunded' if t.is_refunded else 'pending'),
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_sumup(provider, service_type, last_sync, user, request):
    from sumup_provider.models import SumUpTransaction, SumUpConnection
    conn = _get_provider_connection(SumUpConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = SumUpTransaction.objects.filter(connection=conn).order_by('-timestamp')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.timestamp.isoformat() if t.timestamp else '',
        'description': t.type or '', 'amount': float(t.amount) if t.amount else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_qonto(provider, service_type, last_sync, user, request):
    from qonto_provider.models import QontoTransaction, QontoConnection
    conn = _get_provider_connection(QontoConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = QontoTransaction.objects.filter(connection=conn).order_by('-settled_at')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.settled_at.isoformat() if t.settled_at else '',
        'description': t.label or t.operation_type or '', 'amount': _cents_to_units(t.amount_cents),
        'currency': (t.currency or '').upper(), 'side': t.side or '',
        'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'side', 'status'])


def _handle_alma(provider, service_type, last_sync, user, request):
    from alma_provider.models import AlmaPayment, AlmaConnection
    conn = _get_provider_connection(AlmaConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = AlmaPayment.objects.filter(connection=conn).order_by('-created_at_alma')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.created_at_alma.isoformat() if t.created_at_alma else '',
        'description': t.customer_email or '',
        'amount': _cents_to_units(t.purchase_amount),
        'currency': (t.currency or '').upper(),
        'installments': t.installments_count or 0, 'status': t.state or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'installments', 'status'])


# ═══════════════════════════════════════════════════════════════
# Invoicing providers
# ═══════════════════════════════════════════════════════════════

def _handle_evoliz(provider, service_type, last_sync, user, request):
    from evoliz_provider.models import EvolizInvoice, EvolizConnection
    conn = _get_provider_connection(EvolizConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = EvolizInvoice.objects.filter(connection=conn).order_by('-documentdate')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.documentdate.isoformat() if t.documentdate else '',
        'description': t.client_name or '', 'amount': float(t.total_vat_include) if t.total_vat_include else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_pennylane(provider, service_type, last_sync, user, request):
    from pennylane_provider.models import PennylaneCustomerInvoice, PennylaneConnection
    conn = _get_provider_connection(PennylaneConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = PennylaneCustomerInvoice.objects.filter(connection=conn).order_by('-date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.date.isoformat() if t.date else '',
        'description': t.customer_name or '', 'amount': float(t.total) if t.total else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_vosfactures(provider, service_type, last_sync, user, request):
    from vosfactures_provider.models import VosFacturesInvoice, VosFacturesConnection
    conn = _get_provider_connection(VosFacturesConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = VosFacturesInvoice.objects.filter(connection=conn).order_by('-issue_date')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.issue_date.isoformat() if t.issue_date else '',
        'description': '', 'amount': float(t.price_gross) if t.price_gross else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_choruspro(provider, service_type, last_sync, user, request):
    from choruspro_provider.models import ChorusProInvoice, ChorusProConnection
    conn = _get_provider_connection(ChorusProConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = ChorusProInvoice.objects.filter(connection=conn).order_by('-date_facture')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.date_facture.isoformat() if t.date_facture else '',
        'description': t.fournisseur_name or t.destinataire_name or '',
        'amount': float(t.montant_ttc) if t.montant_ttc else 0,
        'currency': (t.devise or 'EUR').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


# ═══════════════════════════════════════════════════════════════
# E-commerce providers
# ═══════════════════════════════════════════════════════════════

def _handle_shopify(provider, service_type, last_sync, user, request):
    from shopify_provider.models import ShopifyOrder, ShopifyConnection
    conn = _get_provider_connection(ShopifyConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = ShopifyOrder.objects.filter(connection=conn).order_by('-created_at_shopify')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.created_at_shopify.isoformat() if t.created_at_shopify else '',
        'description': t.customer_email or '', 'amount': float(t.total_price) if t.total_price else 0,
        'currency': (t.currency or '').upper(), 'status': t.financial_status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_prestashop(provider, service_type, last_sync, user, request):
    from prestashop_provider.models import PrestaShopOrder, PrestaShopConnection
    conn = _get_provider_connection(PrestaShopConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = PrestaShopOrder.objects.filter(connection=conn).order_by('-date_add')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.date_add.isoformat() if t.date_add else '',
        'description': t.payment_method or t.current_state_name or '',
        'amount': float(t.total_paid) if t.total_paid else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])


def _handle_woocommerce(provider, service_type, last_sync, user, request):
    from woocommerce_provider.models import WooCommerceOrder, WooCommerceConnection
    conn = _get_provider_connection(WooCommerceConnection, user)
    if not conn:
        return _empty_response(provider, service_type, last_sync, request)
    qs = WooCommerceOrder.objects.filter(connection=conn).order_by('-date_created')
    items_qs, pagination = _paginate(qs, request)
    items = [{
        'id': t.id, 'date': t.date_created.isoformat() if t.date_created else '',
        'description': t.payment_method or '', 'amount': float(t.total_price) if t.total_price else 0,
        'currency': (t.currency or '').upper(), 'status': t.status or '',
    } for t in items_qs]
    return _response(provider, service_type, last_sync, items, pagination,
                     ['date', 'description', 'amount', 'status'])
