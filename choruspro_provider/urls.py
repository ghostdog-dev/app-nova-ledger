from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.ChorusProConnectView.as_view(), name='choruspro-connect'),
    path('sync/', views.ChorusProSyncView.as_view(), name='choruspro-sync'),
    path('invoices/', views.ChorusProInvoicesView.as_view(), name='choruspro-invoices'),
]
