import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


class PowensClient:
    """REST client for the Powens Banking API."""

    def __init__(self, auth_token=None):
        self.base_url = f'https://{settings.POWENS_DOMAIN}/2.0'
        self.auth_token = auth_token
        self.client = httpx.Client(timeout=30)

    def _headers(self):
        h = {'Content-Type': 'application/json'}
        if self.auth_token:
            h['Authorization'] = f'Bearer {self.auth_token}'
        return h

    def _get(self, path, params=None):
        url = f'{self.base_url}{path}'
        logger.info('Powens GET %s params=%s', path, params)
        resp = self.client.get(url, headers=self._headers(), params=params)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path, data=None):
        url = f'{self.base_url}{path}'
        logger.info('Powens POST %s', path)
        resp = self.client.post(url, headers=self._headers(), json=data)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path):
        url = f'{self.base_url}{path}'
        logger.info('Powens DELETE %s', path)
        resp = self.client.delete(url, headers=self._headers())
        resp.raise_for_status()
        return resp.status_code

    # --- Auth ---

    def create_user(self):
        """Create a new Powens user and get a permanent auth token."""
        data = {
            'client_id': settings.POWENS_CLIENT_ID,
            'client_secret': settings.POWENS_CLIENT_SECRET,
        }
        return self._post('/auth/init', data)

    def get_temporary_code(self):
        """Get a temporary code for the webview redirect."""
        return self._get('/auth/token/code')

    def renew_token(self, powens_user_id):
        """Renew an auth token for an existing user."""
        data = {
            'client_id': settings.POWENS_CLIENT_ID,
            'client_secret': settings.POWENS_CLIENT_SECRET,
            'id_user': powens_user_id,
        }
        return self._post('/auth/renew', data)

    # --- Connections ---

    def list_connections(self):
        return self._get('/users/me/connections')

    def get_connection(self, connection_id):
        return self._get(f'/users/me/connections/{connection_id}')

    def delete_connection(self, connection_id):
        return self._delete(f'/users/me/connections/{connection_id}')

    # --- Accounts ---

    def list_accounts(self):
        return self._get('/users/me/accounts')

    # --- Transactions ---

    def list_transactions(self, account_id=None, min_date=None, max_date=None, limit=1000):
        params = {'limit': limit, 'expand': 'categories'}
        if min_date:
            params['min_date'] = min_date
        if max_date:
            params['max_date'] = max_date

        if account_id:
            path = f'/users/me/accounts/{account_id}/transactions'
        else:
            path = '/users/me/transactions'

        return self._get(path, params=params)
