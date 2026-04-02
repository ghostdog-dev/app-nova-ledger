from django.urls import path

from . import views

app_name = 'stripe_financial'

urlpatterns = [
    # Auth flow
    path('session/', views.create_session_view, name='create-session'),
    path('link/', views.link_accounts_view, name='link-accounts'),

    # Sync & refresh
    path('sync/', views.sync_view, name='sync'),
    path('accounts/<str:account_id>/subscribe/', views.subscribe_transactions_view, name='subscribe'),
    path('accounts/<str:account_id>/refresh/', views.refresh_account_view, name='refresh'),
    path('accounts/<str:account_id>/disconnect/', views.disconnect_view, name='disconnect'),

    # Data (read-only)
    path('accounts/', views.list_accounts_view, name='list-accounts'),
    path('accounts/<str:account_id>/transactions/', views.list_transactions_view, name='list-transactions'),

    # Dev test page
    path('test/', views.test_page_view, name='test-page'),
]
