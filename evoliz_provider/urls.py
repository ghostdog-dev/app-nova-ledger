from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.EvolizConnectView.as_view(), name='evoliz-connect'),
    path('sync/', views.EvolizSyncView.as_view(), name='evoliz-sync'),
    path('invoices/', views.EvolizInvoicesView.as_view(), name='evoliz-invoices'),
    path('purchases/', views.EvolizPurchasesView.as_view(), name='evoliz-purchases'),
    path('payments/', views.EvolizPaymentsView.as_view(), name='evoliz-payments'),
]
