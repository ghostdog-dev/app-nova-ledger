from django.urls import path

from core.views import auth, bank_import, clusters, companies, connections, correlations, dashboard, executions, exports, sources, transactions, unified_transactions, ws_ticket

urlpatterns = [
    # Auth
    path('accounts/login/', auth.login_view),
    path('accounts/register/', auth.register_view),
    path('accounts/logout/', auth.logout_view),
    path('accounts/me/', auth.me_view),
    path('accounts/token/refresh/', auth.token_refresh_view),
    path('accounts/social-login/', auth.social_login_view),
    path('accounts/social-auth-url/', auth.social_auth_url_view),
    path('accounts/clear-session/', auth.clear_session_view),

    # Companies
    path('companies/', companies.company_list_view),
    path('companies/<uuid:company_pk>/', companies.company_detail_view),
    path('companies/<uuid:company_pk>/plan/', companies.company_plan_view),
    path('companies/<uuid:company_pk>/usage/', companies.company_usage_view),
    path('companies/<uuid:company_pk>/members/', companies.company_members_view),
    path('companies/<uuid:company_pk>/members/<int:member_pk>/', companies.company_member_detail_view),

    # Connections (company-scoped)
    path('companies/<uuid:company_pk>/connections/', connections.connection_list_view),
    path('companies/<uuid:company_pk>/connections/oauth/initiate/', connections.oauth_initiate_view),
    path('companies/<uuid:company_pk>/connections/oauth/complete/', connections.oauth_complete_view),
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/check/', connections.connection_check_view),
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/sync/', connections.connection_sync_view),
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/', connections.connection_delete_view),

    # Sources (connection data)
    path('companies/<uuid:company_pk>/connections/<uuid:connection_pk>/data/', sources.connection_data_view),

    # Dashboard
    path('companies/<uuid:company_pk>/dashboard/', dashboard.dashboard_view),

    # Executions
    path('companies/<uuid:company_pk>/executions/', executions.execution_list_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/', executions.execution_detail_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/progress/', executions.execution_progress_view),
    path('companies/<uuid:company_pk>/executions/<uuid:execution_pk>/exports/', exports.create_export_view),

    # Correlations (top-level)
    path('correlations/', correlations.correlation_list_view),
    path('correlations/<uuid:correlation_pk>/', correlations.correlation_detail_view),

    # Exports
    path('exports/<uuid:export_pk>/', exports.export_detail_view),

    # Bank Import
    path('companies/<uuid:company_pk>/bank-import/upload/', bank_import.BankFileUploadView.as_view(), name='bank-import-upload'),
    path('companies/<uuid:company_pk>/bank-import/', bank_import.BankImportListView.as_view(), name='bank-import-list'),

    # Transactions
    path('companies/<uuid:company_pk>/transactions/', transactions.transaction_list_view),

    # Unified transactions
    path('companies/<uuid:company_pk>/unified-transactions/', unified_transactions.UnifiedTransactionListView.as_view(), name='unified-transactions-list'),
    path('companies/<uuid:company_pk>/unified-stats/', unified_transactions.UnifiedStatsView.as_view(), name='unified-stats'),

    # Clusters
    path('companies/<uuid:company_pk>/clusters/', clusters.ClusterListView.as_view(), name='clusters-list'),
    path('companies/<uuid:company_pk>/clusters/<int:pk>/', clusters.ClusterDetailView.as_view(), name='clusters-detail'),
    path('companies/<uuid:company_pk>/clusters/<int:pk>/verify/', clusters.ClusterVerifyView.as_view(), name='clusters-verify'),

    # WebSocket ticket
    path('ws/ticket/', ws_ticket.ws_ticket_view),
]
