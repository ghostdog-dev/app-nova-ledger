from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.VosFacturesConnectView.as_view(), name='vosfactures-connect'),
    path('sync/', views.VosFacturesSyncView.as_view(), name='vosfactures-sync'),
    path('invoices/', views.VosFacturesInvoicesView.as_view(), name='vosfactures-invoices'),
    path('payments/', views.VosFacturesPaymentsView.as_view(), name='vosfactures-payments'),
    path('clients/', views.VosFacturesClientsView.as_view(), name='vosfactures-clients'),
]
