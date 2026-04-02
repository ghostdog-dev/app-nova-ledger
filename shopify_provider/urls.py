from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.ShopifyConnectView.as_view(), name='shopify-connect'),
    path('sync/', views.ShopifySyncView.as_view(), name='shopify-sync'),
    path('orders/', views.ShopifyOrdersView.as_view(), name='shopify-orders'),
]
