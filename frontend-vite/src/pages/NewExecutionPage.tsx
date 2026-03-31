import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, CalendarRange, Loader2, Server, Zap } from 'lucide-react';
import { clsx } from 'clsx';
import { Card } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { getConnections } from '@/hooks/use-connections';
import { createExecution } from '@/hooks/use-executions';
import { useCompanyStore } from '@/stores/company-store';
import { getStoredAccessToken } from '@/lib/api-client';
import type { ServiceConnection } from '@/types';
import styles from './NewExecutionPage.module.css';
import { useNavigate } from 'react-router-dom';


interface FormErrors {
  dateFrom?: string;
  dateTo?: string;
  services?: string;
}

export default function NewExecutionPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [isLoadingConnections, setIsLoadingConnections] = useState(true);

  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedServices, setSelectedServices] = useState<string[]>([]);

  const [errors, setErrors] = useState<FormErrors>({});
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Unified pipeline state
  const [isRunningUnified, setIsRunningUnified] = useState(false);
  const [unifiedResult, setUnifiedResult] = useState<{ stats: unknown } | null>(null);
  const [unifiedError, setUnifiedError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeCompany) return;
    getConnections()
      .then((data) => {
        const active = data.filter((c) => c.status === 'active');
        setConnections(active);
        // Pre-select all active connections
        setSelectedServices(active.map((c) => c.publicId));
      })
      .catch(() => setConnections([]))
      .finally(() => setIsLoadingConnections(false));
  }, [activeCompany]);

  const toggleService = useCallback((id: string) => {
    setSelectedServices((prev) =>
      prev.includes(id) ? prev.filter((s) => s !== id) : [...prev, id]
    );
  }, []);

  const handleUnifiedPipeline = async () => {
    setIsRunningUnified(true);
    setUnifiedResult(null);
    setUnifiedError(null);
    try {
      const token = getStoredAccessToken();
      const headers: Record<string, string> = { 'Content-Type': 'application/json' };
      if (token) headers['Authorization'] = `Bearer ${token}`;
      const response = await fetch('/api/ai/unified-pipeline/', {
        method: 'POST',
        headers,
        credentials: 'include',
      });
      if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.detail || `HTTP ${response.status}`);
      }
      const data = await response.json();
      setUnifiedResult(data);
    } catch (err) {
      setUnifiedError(err instanceof Error ? err.message : t('errors.unknown'));
    } finally {
      setIsRunningUnified(false);
    }
  };

  const validate = (): boolean => {
    const errs: FormErrors = {};
    if (!dateFrom) errs.dateFrom = t('executions.form.validation.dateFromRequired');
    if (!dateTo) errs.dateTo = t('executions.form.validation.dateToRequired');
    if (dateFrom && dateTo && dateTo < dateFrom)
      errs.dateTo = t('executions.form.validation.dateRangeInvalid');
    if (selectedServices.length === 0)
      errs.services = t('executions.form.validation.servicesRequired');
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;

    setIsSubmitting(true);
    setSubmitError(null);
    try {
      const execution = await createExecution({
        dateFrom,
        dateTo,
        includedConnections: selectedServices,
      });
      navigate(`/executions/${execution.publicId}`);
    } catch {
      setSubmitError(t('errors.unknown'));
      setIsSubmitting(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.headerRow}>
        <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className={styles.iconSm} />} onClick={() => navigate('/executions')}>
          {t('common.back')}
        </Button>
        <div>
          <h1 className={styles.title}>{t('executions.form.title')}</h1>
          <p className={styles.subtitle}>{t('executions.form.subtitle')}</p>
        </div>
      </div>

      {/* Unified pipeline */}
      <Card padding="md">
        <div className={styles.sectionHeader}>
          <Zap className={styles.sectionIcon} aria-hidden="true" />
          <h2 className={styles.sectionTitle}>Pipeline Unifie</h2>
        </div>
        <p className={styles.sectionHint}>
          Ingestion, enrichissement, correlation, calcul et verification automatiques de toutes vos sources connectees.
        </p>
        <Button
          onClick={handleUnifiedPipeline}
          disabled={isRunningUnified}
          leftIcon={isRunningUnified ? <Loader2 className={clsx(styles.iconSm, styles.spin)} /> : <Zap className={styles.iconSm} />}
          isLoading={isRunningUnified}
        >
          {isRunningUnified ? 'Pipeline en cours...' : 'Lancer le pipeline unifie'}
        </Button>
        {unifiedResult && (
          <Alert variant="success" className={styles.unifiedResult}>
            Termine — {JSON.stringify(unifiedResult.stats)}
          </Alert>
        )}
        {unifiedError && (
          <Alert variant="error" onClose={() => setUnifiedError(null)}>
            {unifiedError}
          </Alert>
        )}
      </Card>

      {submitError && (
        <Alert variant="error" onClose={() => setSubmitError(null)}>
          {submitError}
        </Alert>
      )}

      <form onSubmit={handleSubmit} noValidate className={styles.form}>
        {/* Date range */}
        <Card padding="md">
          <div className={styles.sectionHeader}>
            <CalendarRange className={styles.sectionIcon} aria-hidden="true" />
            <h2 className={styles.sectionTitle}>
              {t('executions.form.dateRange')}
            </h2>
          </div>
          <div className={styles.dateGrid}>
            <Input
              type="date"
              label={t('executions.form.dateFrom')}
              value={dateFrom}
              onChange={(e) => { setDateFrom(e.target.value); setErrors((p) => ({ ...p, dateFrom: undefined })); }}
              error={errors.dateFrom}
              max={dateTo || undefined}
            />
            <Input
              type="date"
              label={t('executions.form.dateTo')}
              value={dateTo}
              onChange={(e) => { setDateTo(e.target.value); setErrors((p) => ({ ...p, dateTo: undefined })); }}
              error={errors.dateTo}
              min={dateFrom || undefined}
            />
          </div>
        </Card>

        {/* Connections */}
        <Card padding="md">
          <div className={styles.sectionHeader}>
            <Server className={styles.sectionIcon} aria-hidden="true" />
            <h2 className={styles.sectionTitle}>
              {t('executions.form.services')}
            </h2>
          </div>
          <p className={styles.sectionHint}>{t('executions.form.servicesHint')}</p>

          {isLoadingConnections ? (
            <div className={styles.loadingCenter}>
              <Spinner size="sm" />
            </div>
          ) : connections.length === 0 ? (
            <p className={styles.noServices}>{t('executions.form.noServices')}</p>
          ) : (
            <div className={styles.servicesList}>
              {connections.map((conn) => {
                const checked = selectedServices.includes(conn.publicId);
                return (
                  <label
                    key={conn.publicId}
                    className={clsx(
                      styles.serviceLabel,
                      checked && styles.serviceLabelChecked
                    )}
                  >
                    <input
                      type="checkbox"
                      className={styles.serviceCheckbox}
                      checked={checked}
                      onChange={() => {
                        toggleService(conn.publicId);
                        setErrors((p) => ({ ...p, services: undefined }));
                      }}
                    />
                    <span className={styles.serviceName}>
                      {conn.providerName}
                    </span>
                    <span className={styles.serviceType}>
                      {conn.serviceType}
                    </span>
                  </label>
                );
              })}
            </div>
          )}
          {errors.services && (
            <p className={styles.fieldError}>{errors.services}</p>
          )}
        </Card>

        {/* Actions */}
        <div className={styles.actions}>
          <Button variant="ghost" onClick={() => navigate('/executions')} disabled={isSubmitting}>
            {t('executions.form.cancel')}
          </Button>
          <Button type="submit" isLoading={isSubmitting}>
            {t('executions.form.submit')}
          </Button>
        </div>
      </form>
    </div>
  );
}
