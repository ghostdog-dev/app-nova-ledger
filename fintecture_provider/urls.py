from django.urls import path

from . import views

urlpatterns = [
    path('connect/', views.FintectureConnectView.as_view(), name='fintecture-connect'),
    path('sync/', views.FintectureSyncView.as_view(), name='fintecture-sync'),
    path('payments/', views.FintecturePaymentsView.as_view(), name='fintecture-payments'),
    path('settlements/', views.FintectureSettlementsView.as_view(), name='fintecture-settlements'),
]
