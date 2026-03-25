from django.conf import settings
from django.urls import path
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from allauth.socialaccount.providers.google.views import GoogleOAuth2Adapter
from allauth.socialaccount.providers.microsoft.views import MicrosoftGraphOAuth2Adapter
from allauth.socialaccount.providers.oauth2.client import OAuth2Client
from dj_rest_auth.registration.views import SocialLoginView

from accounts.serializers import CustomSocialLoginSerializer


@method_decorator(csrf_exempt, name='dispatch')
class GoogleLogin(SocialLoginView):
    adapter_class = GoogleOAuth2Adapter
    callback_url = settings.OAUTH_CALLBACK_URL
    client_class = OAuth2Client
    serializer_class = CustomSocialLoginSerializer
    authentication_classes = []  # No auth needed for login


@method_decorator(csrf_exempt, name='dispatch')
class MicrosoftLogin(SocialLoginView):
    adapter_class = MicrosoftGraphOAuth2Adapter
    callback_url = settings.OAUTH_CALLBACK_URL
    client_class = OAuth2Client
    serializer_class = CustomSocialLoginSerializer
    authentication_classes = []


urlpatterns = [
    path('google/', GoogleLogin.as_view(), name='google_login'),
    path('microsoft/', MicrosoftLogin.as_view(), name='microsoft_login'),
]
