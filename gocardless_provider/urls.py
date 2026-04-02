from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.GoCardlessConnectView.as_view(), name='gocardless-connect'),
    path('sync/', views.GoCardlessSyncView.as_view(), name='gocardless-sync'),
    path('payments/', views.GoCardlessPaymentsView.as_view(), name='gocardless-payments'),
    path('mandates/', views.GoCardlessMandatesView.as_view(), name='gocardless-mandates'),
    path('subscriptions/', views.GoCardlessSubscriptionsView.as_view(), name='gocardless-subscriptions'),
    path('payouts/', views.GoCardlessPayoutsView.as_view(), name='gocardless-payouts'),
    path('refunds/', views.GoCardlessRefundsView.as_view(), name='gocardless-refunds'),
]
