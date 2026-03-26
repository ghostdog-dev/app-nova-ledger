from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.MollieConnectView.as_view(), name='mollie-connect'),
    path('sync/', views.MollieSyncView.as_view(), name='mollie-sync'),
    path('payments/', views.MolliePaymentsView.as_view(), name='mollie-payments'),
    path('refunds/', views.MollieRefundsView.as_view(), name='mollie-refunds'),
    path('settlements/', views.MollieSettlementsView.as_view(), name='mollie-settlements'),
    path('invoices/', views.MollieInvoicesView.as_view(), name='mollie-invoices'),
]
