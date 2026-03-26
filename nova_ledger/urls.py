from django.contrib import admin
from django.urls import include, path

from accounts.views import callback_page, login_page, session_login_view
from banking.views import BankCallbackView
from emails.views import test_page as emails_test_page

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('dj_rest_auth.urls')),
    path('api/auth/registration/', include('dj_rest_auth.registration.urls')),
    path('api/auth/', include('accounts.urls')),
    path('api/emails/', include('emails.urls')),
    path('api/banking/', include('banking.urls')),
    path('api/paypal/', include('paypal_provider.urls')),
    path('api/stripe/', include('stripe_provider.urls')),
    path('api/mollie/', include('mollie_provider.urls')),
    path('callback/powens/', BankCallbackView.as_view(), name='powens-callback'),
    path('login/', login_page, name='login_page'),
    path('callback/', callback_page, name='callback_page'),
    path('api/auth/session-login/', session_login_view, name='session_login'),
    path('emails/test/', emails_test_page, name='emails_test_page'),
]
