from django.urls import path

from . import views

urlpatterns = [
    path('classify/', views.AIClassifyView.as_view(), name='ai-classify'),
    path('correlate/', views.AICorrelateView.as_view(), name='ai-correlate'),
    path('classify-batch/', views.classify_batch_view, name='classify-batch'),
    path('classify-batch/<int:run_id>/', views.classify_batch_status_view, name='classify-batch-status'),
    path('unified-pipeline/', views.UnifiedPipelineView.as_view(), name='unified-pipeline'),
]
