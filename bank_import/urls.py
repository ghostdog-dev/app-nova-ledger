from django.urls import path

from . import views

urlpatterns = [
    path('upload/', views.BankFileUploadView.as_view(), name='bank-upload'),
    path('preview/', views.BankFilePreviewView.as_view(), name='bank-preview'),
    path('imports/', views.BankImportListView.as_view(), name='bank-imports'),
    path('imports/<int:import_id>/', views.BankImportDeleteView.as_view(), name='bank-import-delete'),
    path('transactions/', views.ImportedTransactionsView.as_view(), name='bank-transactions'),
]
