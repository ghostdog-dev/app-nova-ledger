PROVIDER_REGISTRY = {
    'stripe': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
    },
    'paypal': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['client_id', 'client_secret', 'is_sandbox'],
    },
    'mollie': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
    },
    'fintecture': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['app_id', 'app_secret', 'is_sandbox'],
    },
    'gocardless': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['access_token', 'environment'],
    },
    'payplug': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['secret_key'],
    },
    'sumup': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key', 'merchant_code'],
    },
    'qonto': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['login', 'secret_key'],
    },
    'alma': {
        'service_type': 'payment',
        'auth_type': 'api_key',
        'credential_fields': ['api_key'],
    },
    'evoliz': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['public_key', 'secret_key', 'company_id'],
    },
    'pennylane': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['access_token'],
    },
    'vosfactures': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['api_token', 'account_prefix'],
    },
    'choruspro': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': [
            'client_id', 'client_secret', 'technical_user_id',
            'structure_id', 'is_sandbox',
        ],
    },
    'shopify': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['store_name', 'access_token'],
    },
    'prestashop': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['shop_url', 'api_key'],
    },
    'woocommerce': {
        'service_type': 'invoicing',
        'auth_type': 'api_key',
        'credential_fields': ['shop_url', 'consumer_key', 'consumer_secret'],
    },
}


def get_provider_config(name):
    """Return the config dict for a provider, or None if not found."""
    return PROVIDER_REGISTRY.get(name)


def get_all_providers():
    """Return a list of all providers with their metadata."""
    return [
        {
            'id': name,
            'name': name,
            'service_type': config['service_type'],
            'auth_type': config['auth_type'],
            'credential_fields': config['credential_fields'],
        }
        for name, config in PROVIDER_REGISTRY.items()
    ]
