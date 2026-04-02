from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.QontoConnectView.as_view(), name='qonto-connect'),
    path('sync/', views.QontoSyncView.as_view(), name='qonto-sync'),
    path('bank-accounts/', views.QontoBankAccountsView.as_view(), name='qonto-bank-accounts'),
    path('transactions/', views.QontoTransactionsView.as_view(), name='qonto-transactions'),
]
