import type { ServiceType } from '@/types';

export type AuthMethod = 'oauth' | 'apikey' | 'both';

export interface ServiceDefinition {
  id: string;
  name: string;
  type: ServiceType;
  authMethod: AuthMethod;
  color: string;
  initials: string;
  description: string;
  credentialFields?: string[];
  apiKeyDocsUrl?: string;
}

export const SERVICES_CATALOG: ServiceDefinition[] = [
  // ── Payment ──────────────────────────────────────────────
  {
    id: 'stripe',
    name: 'Stripe',
    type: 'payment',
    authMethod: 'apikey',
    color: '#635BFF',
    initials: 'ST',
    description: 'Paiements en ligne et abonnements',
    credentialFields: ['api_key'],
    apiKeyDocsUrl: 'https://dashboard.stripe.com/apikeys',
  },
  {
    id: 'paypal',
    name: 'PayPal',
    type: 'payment',
    authMethod: 'apikey',
    color: '#003087',
    initials: 'PP',
    description: 'Paiements en ligne internationaux',
    credentialFields: ['client_id', 'client_secret', 'is_sandbox'],
  },
  {
    id: 'mollie',
    name: 'Mollie',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1E293B',
    initials: 'ML',
    description: 'Paiements multi-methodes',
    credentialFields: ['api_key'],
    apiKeyDocsUrl: 'https://my.mollie.com/dashboard/developers/api-keys',
  },
  {
    id: 'fintecture',
    name: 'Fintecture',
    type: 'payment',
    authMethod: 'apikey',
    color: '#059669',
    initials: 'FT',
    description: 'Paiement instantane Open Banking',
    credentialFields: ['app_id', 'app_secret', 'is_sandbox'],
  },
  {
    id: 'gocardless',
    name: 'GoCardless',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1D4ED8',
    initials: 'GC',
    description: 'Prelevements bancaires (SEPA)',
    credentialFields: ['access_token', 'environment'],
  },
  {
    id: 'payplug',
    name: 'PayPlug',
    type: 'payment',
    authMethod: 'apikey',
    color: '#7C3AED',
    initials: 'PG',
    description: 'Paiements pour les commercants francais',
    credentialFields: ['secret_key'],
  },
  {
    id: 'sumup',
    name: 'SumUp',
    type: 'payment',
    authMethod: 'apikey',
    color: '#1A73E8',
    initials: 'SU',
    description: 'Terminaux de paiement et encaissements',
    credentialFields: ['api_key', 'merchant_code'],
  },
  {
    id: 'qonto',
    name: 'Qonto',
    type: 'payment',
    authMethod: 'apikey',
    color: '#4B32C3',
    initials: 'QT',
    description: 'Compte pro et gestion financiere',
    credentialFields: ['login', 'secret_key'],
  },
  {
    id: 'alma',
    name: 'Alma',
    type: 'payment',
    authMethod: 'apikey',
    color: '#FF6B4A',
    initials: 'AL',
    description: 'Paiement en plusieurs fois',
    credentialFields: ['api_key'],
  },

  // ── Invoicing ────────────────────────────────────────────
  {
    id: 'evoliz',
    name: 'Evoliz',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#16A34A',
    initials: 'EV',
    description: 'Facturation et gestion commerciale',
    credentialFields: ['public_key', 'secret_key', 'company_id'],
    apiKeyDocsUrl: 'https://www.evoliz.io/api-documentation',
  },
  {
    id: 'pennylane',
    name: 'Pennylane',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#8B5CF6',
    initials: 'PL',
    description: 'Comptabilite et facturation',
    credentialFields: ['access_token'],
  },
  {
    id: 'vosfactures',
    name: 'VosFactures',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#F59E0B',
    initials: 'VF',
    description: 'Facturation en ligne',
    credentialFields: ['api_token', 'account_prefix'],
  },
  {
    id: 'choruspro',
    name: 'Chorus Pro',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#0F172A',
    initials: 'CP',
    description: 'Facturation secteur public',
    credentialFields: ['client_id', 'client_secret', 'technical_user_id', 'structure_id', 'is_sandbox'],
  },

  // ── E-commerce (enrichment) ──────────────────────────────
  {
    id: 'shopify',
    name: 'Shopify',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#96BF48',
    initials: 'SH',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['store_name', 'access_token'],
  },
  {
    id: 'prestashop',
    name: 'PrestaShop',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#DF0067',
    initials: 'PS',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['shop_url', 'api_key'],
  },
  {
    id: 'woocommerce',
    name: 'WooCommerce',
    type: 'invoicing',
    authMethod: 'apikey',
    color: '#7F54B3',
    initials: 'WC',
    description: 'Commandes et paiements e-commerce',
    credentialFields: ['shop_url', 'consumer_key', 'consumer_secret'],
  },

  // ── Email ────────────────────────────────────────────────
  {
    id: 'gmail',
    name: 'Gmail',
    type: 'email',
    authMethod: 'oauth',
    color: '#EA4335',
    initials: 'GM',
    description: 'Emails et pieces jointes de facturation Google',
  },
  {
    id: 'outlook',
    name: 'Outlook',
    type: 'email',
    authMethod: 'oauth',
    color: '#0078D4',
    initials: 'OL',
    description: 'Emails et pieces jointes de facturation Microsoft',
  },
];

export function getServiceById(id: string): ServiceDefinition | undefined {
  return SERVICES_CATALOG.find((s) => s.id === id);
}

export function getServicesByType(type: ServiceType): ServiceDefinition[] {
  return SERVICES_CATALOG.filter((s) => s.type === type);
}
