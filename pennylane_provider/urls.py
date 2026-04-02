from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.PennylaneConnectView.as_view(), name='pennylane-connect'),
    path('sync/', views.PennylaneSyncView.as_view(), name='pennylane-sync'),
    path('customer-invoices/', views.PennylaneCustomerInvoicesView.as_view(), name='pennylane-customer-invoices'),
    path('supplier-invoices/', views.PennylaneSupplierInvoicesView.as_view(), name='pennylane-supplier-invoices'),
    path('transactions/', views.PennylaneTransactionsView.as_view(), name='pennylane-transactions'),
]
