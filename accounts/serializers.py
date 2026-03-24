from django.contrib.auth import get_user_model
from django.db import IntegrityError
from django.http import HttpResponseBadRequest
from django.utils.translation import gettext_lazy as _

from allauth.account import app_settings as allauth_account_settings
from allauth.account.models import EmailAddress
from allauth.socialaccount import app_settings as socialaccount_settings
from allauth.socialaccount.helpers import complete_social_login
from allauth.socialaccount.providers.oauth2.client import OAuth2Error

from dj_rest_auth.registration.serializers import RegisterSerializer, SocialLoginSerializer
from requests.exceptions import HTTPError
from rest_framework import serializers


class CustomRegisterSerializer(RegisterSerializer):
    username = None

    def get_cleaned_data(self):
        return {
            'email': self.validated_data.get('email', ''),
            'password1': self.validated_data.get('password1', ''),
        }


class CustomSocialLoginSerializer(SocialLoginSerializer):
    def validate(self, attrs):
        view = self.context.get('view')
        request = self._get_request()

        if not view:
            raise serializers.ValidationError(_('View is not defined, pass it as a context variable'))

        adapter_class = getattr(view, 'adapter_class', None)
        if not adapter_class:
            raise serializers.ValidationError(_('Define adapter_class in view'))

        adapter = adapter_class(request)
        app = adapter.get_provider().app

        access_token = attrs.get('access_token')
        code = attrs.get('code')

        if access_token:
            tokens_to_parse = {'access_token': access_token}
            token = access_token
            id_token = attrs.get('id_token')
            if id_token:
                tokens_to_parse['id_token'] = id_token
        elif code:
            self.set_callback_url(view=view, adapter_class=adapter_class)
            self.client_class = getattr(view, 'client_class', None)
            if not self.client_class:
                raise serializers.ValidationError(_('Define client_class in view'))

            client = self.client_class(
                request, app.client_id, app.secret,
                adapter.access_token_method, adapter.access_token_url,
                self.callback_url, scope_delimiter=adapter.scope_delimiter,
                headers=adapter.headers, basic_auth=adapter.basic_auth,
            )
            try:
                token = client.get_access_token(code)
            except OAuth2Error as ex:
                raise serializers.ValidationError(_('Failed to exchange code for access token')) from ex

            access_token = token['access_token']
            tokens_to_parse = {'access_token': access_token}
            for key in ['refresh_token', 'id_token', adapter.expires_in_key]:
                if key in token:
                    tokens_to_parse[key] = token[key]
        else:
            raise serializers.ValidationError(_('Incorrect input. access_token or code is required.'))

        social_token = adapter.parse_token(tokens_to_parse)
        social_token.app = app

        try:
            if adapter.provider_id == 'google' and not code:
                login = self.get_social_login(adapter, app, social_token, response={'id_token': id_token})
            else:
                login = self.get_social_login(adapter, app, social_token, token)
            ret = complete_social_login(request, login)
        except HTTPError:
            raise serializers.ValidationError(_('Incorrect value'))

        if isinstance(ret, HttpResponseBadRequest):
            raise serializers.ValidationError(ret.content)

        if not login.is_existing:
            if allauth_account_settings.UNIQUE_EMAIL:
                User = get_user_model()
                existing_user = User.objects.filter(email=login.user.email).first()
                if existing_user:
                    # Auto-link if email is verified and setting is enabled
                    if socialaccount_settings.EMAIL_AUTHENTICATION:
                        email_verified = EmailAddress.objects.filter(
                            user=existing_user, email=login.user.email, verified=True
                        ).exists()
                        if email_verified:
                            login.user = existing_user
                            login.save(request, connect=True)
                            attrs['user'] = existing_user
                            return attrs
                    raise serializers.ValidationError(
                        _('User is already registered with this e-mail address.'))

            login.lookup()
            try:
                login.save(request, connect=True)
            except IntegrityError as ex:
                raise serializers.ValidationError(
                    _('User is already registered with this e-mail address.')) from ex
            self.post_signup(login, attrs)

        attrs['user'] = login.account.user
        return attrs
