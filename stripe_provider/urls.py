from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.StripeConnectView.as_view(), name='stripe-connect'),
    path('sync/', views.StripeSyncView.as_view(), name='stripe-sync'),
    path('balance-transactions/', views.StripeBalanceTransactionsView.as_view(), name='stripe-balance-transactions'),
    path('charges/', views.StripeChargesView.as_view(), name='stripe-charges'),
    path('payouts/', views.StripePayoutsView.as_view(), name='stripe-payouts'),
    path('invoices/', views.StripeInvoicesView.as_view(), name='stripe-invoices'),
    path('subscriptions/', views.StripeSubscriptionsView.as_view(), name='stripe-subscriptions'),
    path('disputes/', views.StripeDisputesView.as_view(), name='stripe-disputes'),
]
