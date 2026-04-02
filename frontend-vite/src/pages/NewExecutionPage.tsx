import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, Zap, Loader2, Check, AlertTriangle, Database } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { getConnections } from '@/hooks/use-connections';
import { useCompanyStore } from '@/stores/company-store';
import { apiClient } from '@/lib/api-client';
import type { ServiceConnection } from '@/types';
import styles from './NewExecutionPage.module.css';
import { useNavigate } from 'react-router-dom';

const SOURCE_COLORS: Record<string, string> = {
  stripe: '#635BFF', mollie: '#FF6B6B', paypal: '#0070BA',
  gmail: '#EA4335', outlook: '#0078D4', bank_import: '#10B981',
  qonto: '#4B32C3', gocardless: '#1D4ED8',
};

interface PipelineStats {
  ingestion?: { success: boolean; items_processed: number; duration_seconds: number };
  enrichment?: { success: boolean; items_processed: number; duration_seconds: number };
  correlation?: { success: boolean; items_processed: number; clusters_created: number; duration_seconds: number };
  computation?: { success: boolean; items_processed: number; duration_seconds: number };
  verification?: { success: boolean; items_processed: number; anomalies_total: number; duration_seconds: number };
}

const PHASE_LABELS: Record<string, string> = {
  ingestion: 'Ingestion des sources',
  enrichment: 'Enrichissement comptable',
  correlation: 'Corrélation multi-source',
  computation: 'Calculs financiers',
  verification: 'Vérification qualité',
};

export default function NewExecutionPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [isLoadingConnections, setIsLoadingConnections] = useState(true);

  const [isRunning, setIsRunning] = useState(false);
  const [result, setResult] = useState<{ status: string; stats: PipelineStats } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!activeCompany) return;
    getConnections()
      .then((data) => setConnections(data.filter((c) => c.status === 'active')))
      .catch(() => setConnections([]))
      .finally(() => setIsLoadingConnections(false));
  }, [activeCompany]);

  const handleLaunch = async () => {
    setIsRunning(true);
    setError(null);
    try {
      await apiClient.post(`${window.location.origin}/api/ai/unified-pipeline/`);
      navigate('/executions');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : (err as { message?: string })?.message || t('errors.unknown');
      setError(msg);
      setIsRunning(false);
    }
  };

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.headerRow}>
        <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className={styles.iconSm} />} onClick={() => navigate('/executions')}>
          {t('common.back')}
        </Button>
        <div>
          <h1 className={styles.title}>Nouvelle analyse</h1>
          <p className={styles.subtitle}>Lancer le pipeline unifié sur toutes vos sources connectées</p>
        </div>
      </div>

      {/* Connected sources */}
      <Card padding="md">
        <div className={styles.sectionHeader}>
          <Database className={styles.sectionIcon} />
          <h2 className={styles.sectionTitle}>Sources connectées</h2>
        </div>
        {isLoadingConnections ? (
          <div className={styles.loadingCenter}><Spinner size="sm" /></div>
        ) : connections.length === 0 ? (
          <p style={{ opacity: 0.6, fontSize: '0.85rem' }}>
            Aucune source connectée. Ajoutez des services dans la page Connections.
          </p>
        ) : (
          <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
            {connections.map((conn) => (
              <span key={conn.publicId} style={{
                display: 'inline-flex', alignItems: 'center', gap: '0.4rem',
                padding: '0.4rem 0.75rem', borderRadius: '0.5rem',
                background: 'rgba(255,255,255,0.05)', fontSize: '0.8rem',
              }}>
                <span style={{
                  width: '8px', height: '8px', borderRadius: '50%',
                  background: SOURCE_COLORS[conn.providerName] ?? '#6B7280',
                }} />
                {conn.providerName}
                <Check size={12} style={{ color: '#10B981' }} />
              </span>
            ))}
          </div>
        )}
      </Card>

      {/* Launch button */}
      <Card padding="md">
        <div className={styles.sectionHeader}>
          <Zap className={styles.sectionIcon} />
          <h2 className={styles.sectionTitle}>Pipeline unifié</h2>
        </div>
        <p style={{ opacity: 0.6, fontSize: '0.85rem', marginBottom: '1rem' }}>
          5 phases automatiques : ingestion de toutes les sources → enrichissement comptable (PCG, TVA) →
          corrélation multi-source → calculs financiers → vérification qualité.
        </p>
        <Button
          onClick={handleLaunch}
          disabled={isRunning}
          leftIcon={isRunning ? <Loader2 className={styles.iconSm} style={{ animation: 'spin 1s linear infinite' }} /> : <Zap className={styles.iconSm} />}
          fullWidth
        >
          {isRunning ? 'Analyse en cours... (peut prendre quelques minutes)' : 'Lancer l\'analyse'}
        </Button>
      </Card>

      {/* Error */}
      {error && (
        <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>
      )}

      {/* Results */}
      {result && (
        <Card padding="md">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem' }}>
            <Check size={20} style={{ color: '#10B981' }} />
            <h2 style={{ fontWeight: 600 }}>Analyse terminée</h2>
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
            {Object.entries(PHASE_LABELS).map(([phase, label]) => {
              const phaseStats = result.stats[phase as keyof PipelineStats];
              if (!phaseStats) return null;
              const ok = phaseStats.success;
              const duration = (phaseStats as { duration_seconds?: number }).duration_seconds;
              return (
                <div key={phase} style={{
                  display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  padding: '0.5rem 0.75rem', borderRadius: '0.5rem',
                  background: ok ? 'rgba(16,185,129,0.08)' : 'rgba(239,68,68,0.08)',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    {ok ? <Check size={14} style={{ color: '#10B981' }} /> : <AlertTriangle size={14} style={{ color: '#EF4444' }} />}
                    <span style={{ fontSize: '0.85rem' }}>{label}</span>
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.75rem', opacity: 0.6 }}>
                    <span>{phaseStats.items_processed} traités</span>
                    {(phaseStats as { clusters_created?: number }).clusters_created != null && (
                      <span>{(phaseStats as { clusters_created: number }).clusters_created} clusters</span>
                    )}
                    {(phaseStats as { anomalies_total?: number }).anomalies_total != null && (
                      <span>{(phaseStats as { anomalies_total: number }).anomalies_total} anomalies</span>
                    )}
                    {duration != null && <span>{duration < 1 ? '<1s' : `${Math.round(duration)}s`}</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div style={{ marginTop: '1rem' }}>
            <Button size="sm" onClick={() => navigate('/transactions')} leftIcon={<Database className={styles.iconSm} />}>
              Voir le rapport comptable
            </Button>
          </div>
        </Card>
      )}
    </div>
  );
}
