# Providers Roadmap

Liste des services a connecter a Nova Ledger.

## Services de facturation

| Service | Auth | Documentation |
|---------|------|---------------|
| Pennylane | OAuth 2.0 | https://pennylane.readme.io/docs/oauth-20-walkthrough |
| Qonto | OAuth 2.0 | https://docs.qonto.com/get-started/business-api/authentication/oauth/login-endpoint |
| Sellsy | OAuth 2.0 (PKCE) | https://api.sellsy.com/doc/v2 |

## Services de paiement

| Service | Auth | Documentation |
|---------|------|---------------|
| Stripe | OAuth 2.0 (Connect) | https://docs.stripe.com/connect/oauth-reference |
| PayPal | OAuth 2.0 (client credentials) | https://developer.paypal.com/api/rest/authentication/ |
| Mollie | OAuth 2.0 (Connect) | https://docs.mollie.com/reference/oauth-api |
| Qonto | OAuth 2.0 (meme connexion que facturation) | https://docs.qonto.com |
| SumUp | OAuth 2.0 | https://developer.sumup.com/tools/authorization/oauth |
| Lydia (Sumeria) | API Key (PSD2) | https://github.com/LydiaSolutions/psd2-partner-documentation |

## Notes

- Qonto apparait dans les deux categories (facturation + paiement) -- une seule connexion OAuth suffira
- 7 providers sur 8 supportent OAuth 2.0, seul Lydia est en API Key
- PayPal utilise OAuth client credentials (server-to-server), pas un flow user-facing comme les autres
- Stripe recommande Connect Onboarding plutot qu'OAuth pour les nouvelles plateformes, mais OAuth reste utilisable
- SumUp supporte OAuth 2.0 en plus des API Keys (preferer OAuth)
- Sellsy requiert PKCE dans le flow OAuth
- Total : 8 providers uniques, 7 OAuth + 1 API Key
