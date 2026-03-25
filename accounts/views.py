import json
import urllib.parse

from django.conf import settings
from django.contrib.auth import login
from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from allauth.socialaccount.models import SocialApp

from accounts.models import CustomUser


def login_page(request):
    callback_url = settings.OAUTH_CALLBACK_URL

    # Google OAuth URL
    try:
        google_app = SocialApp.objects.get(provider='google')
        google_url = (
            'https://accounts.google.com/o/oauth2/v2/auth?'
            + urllib.parse.urlencode({
                'client_id': google_app.client_id,
                'redirect_uri': callback_url,
                'response_type': 'code',
                'scope': 'email profile https://www.googleapis.com/auth/gmail.readonly',
                'access_type': 'offline',
                'prompt': 'consent',
            })
        )
    except SocialApp.DoesNotExist:
        google_url = None

    # Microsoft OAuth URL
    try:
        ms_app = SocialApp.objects.get(provider='microsoft')
        microsoft_url = (
            'https://login.microsoftonline.com/common/oauth2/v2.0/authorize?'
            + urllib.parse.urlencode({
                'client_id': ms_app.client_id,
                'redirect_uri': callback_url,
                'response_type': 'code',
                'scope': 'openid email profile User.Read Mail.Read offline_access',
            })
        )
    except SocialApp.DoesNotExist:
        microsoft_url = None

    html = f"""<!DOCTYPE html>
<html>
<head><title>Nova Ledger - Login</title></head>
<body style="font-family:sans-serif;max-width:400px;margin:80px auto;text-align:center">
    <h2>Nova Ledger Login</h2>
    {'<a href="' + google_url + '" style="display:block;padding:12px;margin:10px 0;background:#4285f4;color:#fff;text-decoration:none;border-radius:4px">Login with Google</a>' if google_url else '<p>Google not configured</p>'}
    {'<a href="' + microsoft_url + '" style="display:block;padding:12px;margin:10px 0;background:#00a4ef;color:#fff;text-decoration:none;border-radius:4px">Login with Microsoft</a>' if microsoft_url else '<p>Microsoft not configured</p>'}
</body>
</html>"""
    return HttpResponse(html)


def callback_page(request):
    code = request.GET.get('code', '')
    error = request.GET.get('error', '')
    # Detect provider from URL params (Google includes 'scope' with googleapis, Microsoft doesn't)
    scope = request.GET.get('scope', '')
    provider_hint = 'google' if 'googleapis' in scope else 'microsoft'

    html = f"""<!DOCTYPE html>
<html>
<head><title>OAuth Callback</title></head>
<body style="font-family:sans-serif;max-width:600px;margin:80px auto">
    <h2>OAuth Callback</h2>
    <div id="status">Processing...</div>
    <pre id="result" style="background:#f0f0f0;padding:12px;border-radius:4px;white-space:pre-wrap"></pre>
    <p><a href="/login/">Back to login</a></p>
    <p><a href="/emails/test/">Go to Email Test Page</a></p>
    <script>
        const code = "{code}";
        const error = "{error}";
        const providerHint = "{provider_hint}";
        const statusEl = document.getElementById('status');
        const resultEl = document.getElementById('result');

        if (error) {{
            statusEl.textContent = 'Error: ' + error;
        }} else if (code) {{
            async function tryLogin() {{
                // Try the detected provider first, then the other
                const providers = providerHint === 'google' ? ['google', 'microsoft'] : ['microsoft', 'google'];
                for (const provider of providers) {{
                    try {{
                        const resp = await fetch('/api/auth/' + provider + '/', {{
                            method: 'POST',
                            headers: {{'Content-Type': 'application/json'}},
                            body: JSON.stringify({{code: code}})
                        }});
                        const data = await resp.json();
                        if (resp.ok) {{
                            // Now create a Django session via the session-login endpoint
                            if (data.user && data.user.pk) {{
                                await fetch('/api/auth/session-login/', {{
                                    method: 'POST',
                                    headers: {{'Content-Type': 'application/json'}},
                                    body: JSON.stringify({{user_pk: data.user.pk}})
                                }});
                            }}
                            statusEl.textContent = 'Logged in via ' + provider + '! You can now use the Email Test Page.';
                            resultEl.textContent = JSON.stringify(data, null, 2);
                            return;
                        }}
                        if (resp.status >= 500) {{
                            statusEl.textContent = provider + ' error';
                            resultEl.textContent = JSON.stringify(data, null, 2);
                            return;
                        }}
                    }} catch(e) {{
                        console.log(provider + ' failed:', e);
                    }}
                }}
                statusEl.textContent = 'Login failed with both providers';
            }}
            tryLogin();
        }} else {{
            statusEl.textContent = 'No code received';
        }}
    </script>
</body>
</html>"""
    return HttpResponse(html)


@csrf_exempt
@require_POST
def session_login_view(request):
    """Dev-only: create a Django session after OAuth JWT login.
    This allows the test pages to use SessionAuthentication."""
    if not settings.DEBUG:
        return JsonResponse({"error": "only available in debug mode"}, status=403)
    try:
        data = json.loads(request.body)
        user = CustomUser.objects.get(pk=data['user_pk'])
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        return JsonResponse({"ok": True})
    except (CustomUser.DoesNotExist, KeyError, json.JSONDecodeError):
        return JsonResponse({"error": "invalid request"}, status=400)
