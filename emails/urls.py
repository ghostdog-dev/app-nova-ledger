from django.urls import path

from . import views

urlpatterns = [
    path('sync/', views.EmailSyncView.as_view(), name='email_sync'),
    path('classify/', views.EmailClassifyView.as_view(), name='email_classify'),
    path('', views.EmailListView.as_view(), name='email_list'),
    path('transactions/', views.TransactionListView.as_view(), name='transaction_list'),
]
