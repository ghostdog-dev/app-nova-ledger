from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.PayPlugConnectView.as_view(), name='payplug-connect'),
    path('sync/', views.PayPlugSyncView.as_view(), name='payplug-sync'),
    path('payments/', views.PayPlugPaymentsView.as_view(), name='payplug-payments'),
    path('refunds/', views.PayPlugRefundsView.as_view(), name='payplug-refunds'),
]
