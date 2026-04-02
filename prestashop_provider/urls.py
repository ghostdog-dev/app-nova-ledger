from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.PrestaShopConnectView.as_view(), name='prestashop-connect'),
    path('sync/', views.PrestaShopSyncView.as_view(), name='prestashop-sync'),
    path('orders/', views.PrestaShopOrdersView.as_view(), name='prestashop-orders'),
    path('payments/', views.PrestaShopPaymentsView.as_view(), name='prestashop-payments'),
]
