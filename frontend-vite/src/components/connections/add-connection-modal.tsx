import { useState, useCallback, useEffect, useRef, useMemo, type ChangeEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { X, ChevronRight, CheckCircle, Search } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Alert } from '@/components/ui/alert';
import { ServiceIcon } from './service-icon';
import { SERVICES_CATALOG, getServicesByType } from '@/lib/services-catalog';
import { initiateOAuth, connectApiKey as connectApiKeyFn } from '@/hooks/use-connections';
import type { ServiceType } from '@/types';
import type { ServiceDefinition } from '@/lib/services-catalog';
import styles from './add-connection-modal.module.css';

/** Convert snake_case field name to a readable label (e.g. 'api_key' → 'API Key') */
function formatFieldLabel(field: string): string {
  return field
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ');
}

interface AddConnectionModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (serviceId: string) => void;
}

type Step = 1 | 2 | 3 | 'success';

const SERVICE_TYPE_OPTIONS: { type: ServiceType; emoji: string; descriptionKey: string }[] = [
  { type: 'invoicing', emoji: '\uD83E\uDDFE', descriptionKey: 'Pennylane, Sellsy, QuickBooks\u2026' },
  { type: 'payment', emoji: '\uD83D\uDCB3', descriptionKey: 'Stripe, GoCardless, PayPal\u2026' },
  { type: 'email', emoji: '\uD83D\uDCE7', descriptionKey: 'Gmail, Outlook' },
  { type: 'banking', emoji: '\uD83C\uDFE6', descriptionKey: 'Stripe Financial, Import CSV/OFX…' },
];

export function AddConnectionModal({ open, onClose, onSuccess }: AddConnectionModalProps) {
  const { t } = useTranslation();
  const overlayRef = useRef<HTMLDivElement>(null);
  const firstFocusRef = useRef<HTMLButtonElement>(null);

  const [step, setStep] = useState<Step>(1);
  const [selectedType, setSelectedType] = useState<ServiceType | null>(null);
  const [selectedService, setSelectedService] = useState<ServiceDefinition | null>(null);
  const [credentials, setCredentials] = useState<Record<string, string>>({});
  const [credentialErrors, setCredentialErrors] = useState<Record<string, string>>({});
  const [isConnecting, setIsConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploadResult, setUploadResult] = useState<{rowsImported: number; bankName: string} | null>(null);

  // Reset on open
  useEffect(() => {
    if (open) {
      setStep(1);
      setSelectedType(null);
      setSelectedService(null);
      setCredentials({});
      setCredentialErrors({});
      setError(null);
      setSearchQuery('');
      setSelectedFile(null);
      setUploadResult(null);
      setTimeout(() => firstFocusRef.current?.focus(), 50);
    }
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handle = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handle);
    return () => document.removeEventListener('keydown', handle);
  }, [open, onClose]);

  const handleSelectType = (type: ServiceType) => {
    setSelectedType(type);
    setStep(2);
  };

  const handleSelectService = (service: ServiceDefinition) => {
    setSelectedService(service);
    setSearchQuery('');
    setStep(3);
  };

  const handleConnectOAuth = async () => {
    if (!selectedService || !selectedType) return;
    setIsConnecting(true);
    setError(null);
    try {
      const redirectUri = `${window.location.origin}/auth/callback`;
      const { authorizationUrl, state } = await initiateOAuth(selectedService.id, redirectUri);

      // Store state + provider in sessionStorage for CSRF validation on callback
      sessionStorage.setItem('oauth_state', state);
      sessionStorage.setItem('oauth_provider', selectedService.id);

      // F02 — Validate the authorization URL before redirecting
      try {
        const parsed = new URL(authorizationUrl);
        if (parsed.protocol !== 'https:' && parsed.protocol !== 'http:') {
          setError('URL d\'autorisation invalide');
          return;
        }
      } catch {
        setError('URL d\'autorisation invalide');
        return;
      }

      // Redirect user to the OAuth provider
      window.location.href = authorizationUrl;
    } catch {
      setError(t('errors.unknown'));
    } finally {
      setIsConnecting(false);
    }
  };

  const handleConnectApiKey = async () => {
    if (!selectedService || !selectedType) return;
    const fields = selectedService.credentialFields ?? ['api_key'];
    const errors: Record<string, string> = {};
    for (const field of fields) {
      if (!credentials[field]?.trim()) {
        errors[field] = `${formatFieldLabel(field)} requis`;
      }
    }
    if (Object.keys(errors).length > 0) {
      setCredentialErrors(errors);
      return;
    }
    setIsConnecting(true);
    setError(null);
    try {
      await connectApiKeyFn(selectedService.id, selectedType, credentials);
      setStep('success');
      onSuccess(selectedService.id);
    } catch {
      setError(t('errors.unknown'));
    } finally {
      setIsConnecting(false);
    }
  };

  const handleFileUpload = async () => {
    if (!selectedFile) return;
    setIsConnecting(true);
    setError(null);
    try {
      const formData = new FormData();
      formData.append('file', selectedFile);

      // Get company ID and token
      const { useCompanyStore } = await import('@/stores/company-store');
      const activeCompany = useCompanyStore.getState().activeCompany;
      if (!activeCompany) throw new Error('No active company');

      const { getStoredAccessToken } = await import('@/lib/api-client');
      const token = getStoredAccessToken();

      const apiBase = import.meta.env.VITE_API_URL ?? '/api/v1';
      const resp = await fetch(`${apiBase}/companies/${activeCompany.publicId}/bank-import/upload/`, {
        method: 'POST',
        headers: token ? { 'Authorization': `Bearer ${token}` } : {},
        credentials: 'include',
        body: formData,
      });

      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || err.detail || `Upload failed (${resp.status})`);
      }

      const result = await resp.json();
      setUploadResult({ rowsImported: result.rowsImported ?? result.rows_imported ?? 0, bankName: result.bankName ?? result.bank_name ?? '' });
      setStep('success');
      onSuccess('bank_import');
    } catch (e: any) {
      setError(e.message || 'Erreur lors de l\'import');
    } finally {
      setIsConnecting(false);
    }
  };

  const handleBack = useCallback(() => {
    if (step === 2) { setStep(1); setSelectedType(null); setSearchQuery(''); }
    if (step === 3) { setStep(2); setSelectedService(null); setCredentials({}); setCredentialErrors({}); }
  }, [step]);

  // Filtered services for step 2
  const filteredServices = useMemo(() => {
    const base = selectedType ? getServicesByType(selectedType) : SERVICES_CATALOG;
    if (!searchQuery.trim()) return base;
    const q = searchQuery.toLowerCase();
    return base.filter((s) => s.name.toLowerCase().includes(q) || s.description.toLowerCase().includes(q));
  }, [selectedType, searchQuery]);

  if (!open) return null;

  const stepTitle =
    step === 1 ? t('connections.addModal.step1Title')
    : step === 2 ? t('connections.addModal.step2Title')
    : step === 3 ? t('connections.addModal.step3Title')
    : t('connections.addModal.successTitle');

  return (
    <div
      ref={overlayRef}
      className={styles.overlay}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      {/* Backdrop */}
      <div
        className={styles.backdrop}
        onClick={onClose}
        aria-hidden="true"
      />

      {/* Panel */}
      <div className={styles.panel}>
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h2 id="modal-title" className={styles.headerTitle}>
              {stepTitle}
            </h2>
            {step !== 'success' && (
              <p className={styles.headerStep}>
                {t('common.step', { current: typeof step === 'number' ? step : 3, total: 3 })}
              </p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className={styles.closeBtn}
            aria-label={t('common.close')}
          >
            <X className={styles.closeIcon} />
          </button>
        </div>

        {/* Progress bar */}
        {typeof step === 'number' && (
          <div className={styles.progressBar}>
            <div
              className={styles.progressFill}
              style={{ width: `${(step / 3) * 100}%` }}
            />
          </div>
        )}

        {/* Body */}
        <div className={styles.body}>
          {/* Error */}
          {error && (
            <Alert variant="error" className={styles.alertWrap} onClose={() => setError(null)}>
              {error}
            </Alert>
          )}

          {/* Step 1 — Type selection */}
          {step === 1 && (
            <div className={styles.stepGroup}>
              <p className={styles.stepSubtitle}>{t('connections.addModal.step1Subtitle')}</p>
              {SERVICE_TYPE_OPTIONS.map(({ type, emoji, descriptionKey }) => (
                <button
                  key={type}
                  ref={type === 'invoicing' ? firstFocusRef : undefined}
                  type="button"
                  onClick={() => handleSelectType(type)}
                  className={styles.typeBtn}
                >
                  <span className={styles.typeEmoji} aria-hidden="true">{emoji}</span>
                  <div style={{ flex: 1 }}>
                    <p className={styles.typeName}>
                      {t(`connections.types.${type}` as Parameters<typeof t>[0])}
                    </p>
                    <p className={styles.typeDesc}>{descriptionKey}</p>
                  </div>
                  <ChevronRight className={styles.typeChevron} aria-hidden="true" />
                </button>
              ))}
            </div>
          )}

          {/* Step 2 — Service selection */}
          {step === 2 && selectedType && (
            <div className={styles.stepGroup}>
              <p className={styles.stepSubtitle}>
                {t('connections.addModal.step2Subtitle', {
                  type: t(`connections.types.${selectedType}` as Parameters<typeof t>[0]),
                })}
              </p>
              {/* Search */}
              <Input
                type="search"
                placeholder="Rechercher un service\u2026"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                leftIcon={<Search style={{ width: '1rem', height: '1rem' }} />}
                autoComplete="off"
              />
              {filteredServices.length === 0 ? (
                <p className={styles.noResults}>Aucun service trouv\u00e9</p>
              ) : (
                <div className={styles.serviceGrid}>
                  {filteredServices.map((service) => (
                    <button
                      key={service.id}
                      type="button"
                      onClick={() => handleSelectService(service)}
                      className={styles.serviceBtn}
                    >
                      <ServiceIcon service={service} size="md" />
                      <span className={styles.serviceName}>{service.name}</span>
                      <span className={styles.serviceAuth}>
                        {t(`connections.authMethods.${service.authMethod === 'both' ? 'oauth' : service.authMethod}` as Parameters<typeof t>[0])}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}

          {/* Step 3 — Authentication */}
          {step === 3 && selectedService && (
            <div className={styles.stepGroup}>
              <div className={styles.step3Header}>
                <ServiceIcon service={selectedService} size="lg" />
                <div>
                  <p className={styles.step3Name}>{selectedService.name}</p>
                  <p className={styles.step3Desc}>{selectedService.description}</p>
                </div>
              </div>

              {(selectedService.authMethod === 'oauth' || selectedService.authMethod === 'both') && (
                <div className={styles.oauthBox}>
                  <p className={styles.oauthInfo}>
                    {t('connections.addModal.oauthInfo', { service: selectedService.name })}
                  </p>
                  <Button
                    fullWidth
                    isLoading={isConnecting}
                    onClick={handleConnectOAuth}
                  >
                    {t('connections.addModal.connectOAuth', { service: selectedService.name })}
                  </Button>
                </div>
              )}

              {selectedService.authMethod === 'both' && (
                <div className={styles.divider}>
                  <div className={styles.dividerLine} />
                  <span className={styles.dividerText}>{t('common.or')}</span>
                  <div className={styles.dividerLine} />
                </div>
              )}

              {(selectedService.authMethod === 'apikey' || selectedService.authMethod === 'both') && (
                <div className={styles.apiKeyGroup}>
                  {(selectedService.credentialFields ?? ['api_key']).map((field) => (
                    <Input
                      key={field}
                      label={formatFieldLabel(field)}
                      placeholder={formatFieldLabel(field)}
                      value={credentials[field] ?? ''}
                      onChange={(e) => {
                        setCredentials((prev) => ({ ...prev, [field]: e.target.value }));
                        setCredentialErrors((prev) => { const next = { ...prev }; delete next[field]; return next; });
                      }}
                      error={credentialErrors[field]}
                      type={field.includes('secret') || field.includes('key') || field.includes('token') || field.includes('password') ? 'password' : 'text'}
                      autoComplete="off"
                    />
                  ))}
                  {selectedService.apiKeyDocsUrl && (
                    <p style={{ fontSize: '0.75rem', opacity: 0.6 }}>
                      {t('connections.addModal.apiKeyHelp', { service: selectedService.name })}
                    </p>
                  )}
                  <Button
                    fullWidth
                    isLoading={isConnecting}
                    onClick={handleConnectApiKey}
                    variant={selectedService.authMethod === 'both' ? 'secondary' : 'primary'}
                  >
                    {t('connections.addModal.connectApiKey')}
                  </Button>
                </div>
              )}

              {selectedService.authMethod === 'file_upload' && (
                <div className={styles.apiKeyGroup}>
                  <p style={{ fontSize: '0.875rem', opacity: 0.7, marginBottom: '0.75rem' }}>
                    Importez votre relevé bancaire (CSV, OFX, QFX, XML ou PDF)
                  </p>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".csv,.ofx,.qfx,.xml,.pdf"
                    style={{ display: 'none' }}
                    onChange={(e) => {
                      if (e.target.files?.[0]) setSelectedFile(e.target.files[0]);
                    }}
                  />
                  <div
                    onClick={() => fileInputRef.current?.click()}
                    style={{
                      border: '2px dashed rgba(255,255,255,0.2)',
                      borderRadius: '0.75rem',
                      padding: '2rem',
                      textAlign: 'center',
                      cursor: 'pointer',
                      marginBottom: '1rem',
                    }}
                  >
                    {selectedFile ? (
                      <p style={{ color: '#10B981' }}>{'\u2713'} {selectedFile.name}</p>
                    ) : (
                      <p style={{ opacity: 0.6 }}>Cliquez ou glissez un fichier ici</p>
                    )}
                  </div>
                  {selectedFile && (
                    <Button
                      fullWidth
                      isLoading={isConnecting}
                      onClick={handleFileUpload}
                    >
                      Importer {selectedFile.name}
                    </Button>
                  )}
                  {uploadResult && uploadResult.rowsImported > 0 && (
                    <Alert variant="success" style={{ marginTop: '0.75rem' }}>
                      {uploadResult.rowsImported} lignes importées{uploadResult.bankName ? ` (${uploadResult.bankName})` : ''}
                    </Alert>
                  )}
                  {uploadResult && uploadResult.rowsImported === 0 && (
                    <Alert variant="info" style={{ marginTop: '0.75rem' }}>
                      Fichier reçu, traitement en cours par l'IA. Consultez la page Connections pour suivre l'état.
                    </Alert>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Success */}
          {step === 'success' && selectedService && (
            <div className={styles.successWrap}>
              <div className={styles.successIconWrap}>
                <CheckCircle className={styles.successIcon} aria-hidden="true" />
              </div>
              <div>
                <p className={styles.successTitle}>
                  {t('connections.addModal.successTitle')}
                </p>
                <p className={styles.successMsg}>
                  {t('connections.addModal.successMessage', { service: selectedService.name })}
                </p>
              </div>
              <Button onClick={onClose} fullWidth>
                {t('common.close')}
              </Button>
            </div>
          )}
        </div>

        {/* Footer (back/cancel navigation) */}
        {typeof step === 'number' && step > 1 && (
          <div className={styles.footer}>
            <Button variant="ghost" onClick={handleBack}>
              &larr; {t('connections.addModal.back')}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
