# Nova Ledger

## Project Overview
Backend Django API (no frontend). Currently phase 1: authentication system.

## Tech Stack
- Python 3.13 / Django 6.0 / DRF
- django-allauth (Google + Microsoft OAuth)
- dj-rest-auth (REST auth endpoints)
- djangorestframework-simplejwt (JWT tokens)
- python-dotenv

## Project Structure
```
nova-ledger/
  manage.py
  requirements.txt
  .env / .env.example
  nova_ledger/          # Django project
    settings.py
    urls.py
    wsgi.py / asgi.py
  accounts/             # Custom auth app
    models.py           # CustomUser (email-based, no username)
    managers.py         # CustomUserManager
    serializers.py      # CustomRegisterSerializer, CustomSocialLoginSerializer
    urls.py             # OAuth social login views (Google, Microsoft)
    admin.py
  docs/specs/           # Design specs
```

## Auth Architecture
- Custom User: email as unique identifier, no username field
- JWT stateless auth (access + refresh tokens via HttpOnly cookies)
- OAuth providers: Google + Microsoft via allauth
- OAuth tokens stored in DB (SOCIALACCOUNT_STORE_TOKENS = True) for future email reading
- SocialApp credentials stored in DB (not in settings.py) to avoid allauth save issues
- Auto-linking accounts by verified email (CustomSocialLoginSerializer overrides dj-rest-auth to support this)

## API Endpoints
All under `/api/auth/`:
- `POST registration/` - email/password signup
- `POST login/` - email/password login (returns JWT)
- `POST logout/`
- `POST token/refresh/` - refresh JWT
- `POST password/change/`
- `POST password/reset/`
- `POST google/` - Google OAuth (send code, get JWT)
- `POST microsoft/` - Microsoft OAuth (send code, get JWT)
- `POST registration/verify-email/` - confirm email

## Key Design Decisions
- AUTH_USER_MODEL must be set before first migration
- OAuth scopes include email read permissions (gmail.readonly, Mail.Read) requested at login
- Google needs `access_type: offline` and Microsoft needs `offline_access` scope for refresh tokens
- Microsoft requires `User.Read` scope for profile fetching via Graph API
- dj-rest-auth blocks auto-linking by email by default; CustomSocialLoginSerializer overrides this behavior when SOCIALACCOUNT_EMAIL_AUTHENTICATION is enabled
- OAUTH_CALLBACK_URL env var configures the redirect URI for OAuth code exchange

## Setup
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in secrets
python manage.py migrate
python manage.py createsuperuser
# Create SocialApp entries via admin for Google and Microsoft
python manage.py runserver
```

## Important Notes
- SocialApp entries (Google, Microsoft) must exist in DB with correct client_id/secret and linked to Site
- EMAIL_BACKEND is console in dev (emails printed to terminal)
- ACCOUNT_EMAIL_VERIFICATION = 'mandatory' -- users must verify email before login
- Secrets in .env, never committed
