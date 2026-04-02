from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.AlmaConnectView.as_view(), name='alma-connect'),
    path('sync/', views.AlmaSyncView.as_view(), name='alma-sync'),
    path('payments/', views.AlmaPaymentsView.as_view(), name='alma-payments'),
]
