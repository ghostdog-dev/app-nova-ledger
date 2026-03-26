from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.PayPalConnectView.as_view(), name='paypal-connect'),
    path('sync/', views.PayPalSyncView.as_view(), name='paypal-sync'),
    path('transactions/', views.PayPalTransactionsView.as_view(), name='paypal-transactions'),
    path('invoices/', views.PayPalInvoicesView.as_view(), name='paypal-invoices'),
]
