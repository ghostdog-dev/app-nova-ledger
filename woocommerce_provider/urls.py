from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.WooCommerceConnectView.as_view(), name='woocommerce-connect'),
    path('sync/', views.WooCommerceSyncView.as_view(), name='woocommerce-sync'),
    path('orders/', views.WooCommerceOrdersView.as_view(), name='woocommerce-orders'),
]
