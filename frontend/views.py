import os

from django.conf import settings
from django.http import FileResponse, Http404, HttpResponse
from django.views.decorators.cache import never_cache


@never_cache
def index_view(request):
    """Serve the React app's index.html for all frontend routes."""
    index_path = os.path.join(settings.BASE_DIR, 'frontend', 'templates', 'frontend', 'index.html')
    if os.path.exists(index_path):
        with open(index_path, 'r') as f:
            return HttpResponse(f.read(), content_type='text/html')
    return HttpResponse(
        '<h1>Frontend not built</h1><p>Run <code>cd frontend-vite &amp;&amp; npm run build</code></p>',
        content_type='text/html',
    )


def static_asset_view(request, path):
    """Serve Vite build assets (JS, CSS, images)."""
    file_path = os.path.join(settings.BASE_DIR, 'frontend', 'static', 'frontend', 'assets', path)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'))
    raise Http404


def static_root_file_view(request, filename):
    """Serve static files at the root of the build (vite.svg, favicon, etc.)."""
    file_path = os.path.join(settings.BASE_DIR, 'frontend', 'static', 'frontend', filename)
    if os.path.exists(file_path):
        return FileResponse(open(file_path, 'rb'))
    raise Http404
