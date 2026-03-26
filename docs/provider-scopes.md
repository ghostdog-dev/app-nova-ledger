# Provider API Scopes & Permissions Required

## Stripe
**Auth**: API Secret Key (sk_test_ or sk_live_)
**How to get**: https://dashboard.stripe.com/apikeys
**Permissions**: Full access with secret key. For restricted keys, enable:
- Balance Transactions: Read
- Charges: Read
- Payouts: Read
- Invoices: Read
- Subscriptions: Read
- Disputes: Read

## PayPal
**Auth**: Client ID + Client Secret (OAuth2 client_credentials)
**How to get**: https://developer.paypal.com/dashboard/applications
**App type**: Merchant
**Required scopes/features** (enable in app settings):
- **Transaction Search** — required for `/v1/reporting/transactions`
- **Invoicing** — required for `/v2/invoicing/invoices`
- Disputes are available by default

**Sandbox**: Use sandbox app credentials. Some features may take minutes to activate.
**Production**: Use live app credentials.

## Mollie
**Auth**: API Key (test_ or live_)
**How to get**: https://my.mollie.com/dashboard/developers/api-keys
**Endpoints by key type**:

| Endpoint | Test key (test_) | Live key (live_) |
|----------|-----------------|------------------|
| /v2/payments | ✅ | ✅ |
| /v2/refunds | ✅ | ✅ |
| /v2/methods | ✅ | ✅ |
| /v2/organizations/me | ❌ (live only) | ✅ |
| /v2/settlements | ❌ (live only or OAuth) | ✅ |
| /v2/invoices | ❌ (live only or OAuth) | ✅ |

**Note**: Settlements and invoices are Mollie's billing to the merchant (fees).
They are only available with live keys or Mollie Connect OAuth.

## Powens (Banking)
**Auth**: OAuth2 via webview redirect
**How to get**: https://console.powens.com
**Scopes**: Automatic (AIS — Account Information Service)
**Data available**: accounts, transactions, categories
**Note**: Bank consent expires every 180 days (PSD2). User must re-authenticate.
