from django.urls import path, re_path

from . import views

urlpatterns = [
    path('assets/<path:path>', views.static_asset_view),
    re_path(r'^(?P<filename>[^/]+\.\w+)$', views.static_root_file_view),
    re_path(r'^.*$', views.index_view),
]
