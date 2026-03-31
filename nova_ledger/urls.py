from django.contrib import admin
from django.urls import include, path, re_path

from banking.views import BankCallbackView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API v1 — unified API for the React frontend
    path('api/v1/', include('core.urls')),

    # Legacy provider APIs — used internally by core views
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/emails/', include('emails.urls')),
    path('api/banking/', include('banking.urls')),
    path('api/paypal/', include('paypal_provider.urls')),
    path('api/stripe/', include('stripe_provider.urls')),
    path('api/mollie/', include('mollie_provider.urls')),
    path('api/fintecture/', include('fintecture_provider.urls')),
    path('api/gocardless/', include('gocardless_provider.urls')),
    path('api/payplug/', include('payplug_provider.urls')),
    path('api/sumup/', include('sumup_provider.urls')),
    path('api/bank-import/', include('bank_import.urls')),
    path('api/evoliz/', include('evoliz_provider.urls')),
    path('api/pennylane/', include('pennylane_provider.urls')),
    path('api/vosfactures/', include('vosfactures_provider.urls')),
    path('api/qonto/', include('qonto_provider.urls')),
    path('api/shopify/', include('shopify_provider.urls')),
    path('api/prestashop/', include('prestashop_provider.urls')),
    path('api/woocommerce/', include('woocommerce_provider.urls')),
    path('api/alma/', include('alma_provider.urls')),
    path('api/choruspro/', include('choruspro_provider.urls')),
    path('api/ai/', include('ai_agent.urls')),
    path('financial/', include('stripe_financial.urls')),
    path('callback/powens/', BankCallbackView.as_view(), name='powens-callback'),

    # Catch-all: serve React frontend for all non-API routes
    re_path(r'^(?!api/|admin/|financial/|callback/).*', include('frontend.urls')),
]
