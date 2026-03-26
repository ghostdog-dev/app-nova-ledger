from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.BankConnectView.as_view(), name='bank-connect'),
    path('callback/', views.BankCallbackView.as_view(), name='bank-callback'),
    path('sync/', views.BankSyncView.as_view(), name='bank-sync'),
    path('accounts/', views.BankAccountsView.as_view(), name='bank-accounts'),
    path('transactions/', views.BankTransactionsView.as_view(), name='bank-transactions'),
    path('disconnect/<int:connection_id>/', views.BankDisconnectView.as_view(), name='bank-disconnect'),
]
