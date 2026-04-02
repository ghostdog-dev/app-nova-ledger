from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.SumUpConnectView.as_view(), name='sumup-connect'),
    path('sync/', views.SumUpSyncView.as_view(), name='sumup-sync'),
    path('transactions/', views.SumUpTransactionsView.as_view(), name='sumup-transactions'),
    path('payouts/', views.SumUpPayoutsView.as_view(), name='sumup-payouts'),
]
