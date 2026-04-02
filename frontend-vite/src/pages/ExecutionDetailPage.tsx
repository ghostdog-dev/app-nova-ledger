import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowLeft, ArrowRight, Database, GitMerge, TrendingUp, Loader2 } from 'lucide-react';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Spinner } from '@/components/ui/spinner';
import { ExecutionProgressBar } from '@/components/executions/execution-progress';
import { getExecution } from '@/hooks/use-executions';
import { useExecutionProgress } from '@/hooks/use-execution-progress';
import { useCompanyStore } from '@/stores/company-store';
import { companyApi } from '@/lib/company-api';
import { formatDate } from '@/lib/utils';
import type { Execution, ExecutionSummary } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './ExecutionDetailPage.module.css';
import { useNavigate, useParams, Link } from 'react-router-dom';

const STATUS_VARIANT: Record<string, BadgeVariant> = {
  pending: 'default', running: 'info', completed: 'success', failed: 'error',
};

interface UnifiedStats {
  totalTransactions: number;
  clustered: number;
  orphan: number;
  enriched: number;
  clusters: number;
  completeClusters: number;
  averageScore: number;
  bySource: Record<string, number>;
}

const SOURCE_NAMES: Record<string, string> = {
  stripe: 'Stripe', mollie: 'Mollie', paypal: 'PayPal',
  bank_api: 'Banque', bankApi: 'Banque',
  bank_import: 'Import', bankImport: 'Import',
  email: 'Email',
};
const SOURCE_COLORS: Record<string, string> = {
  stripe: '#635BFF', mollie: '#FF6B6B', paypal: '#0070BA',
  bank_api: '#10B981', bankApi: '#10B981',
  bank_import: '#6366F1', bankImport: '#6366F1',
  email: '#8B5CF6',
};

function ScoreCircle({ score }: { score: number }) {
  const color = score >= 80 ? '#10B981' : score >= 50 ? '#F59E0B' : '#EF4444';
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;
  return (
    <div style={{ position: 'relative', width: '100px', height: '100px' }}>
      <svg width="100" height="100" viewBox="0 0 100 100">
        <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.1)" strokeWidth="8" />
        <circle cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circumference} strokeDashoffset={offset}
          strokeLinecap="round" transform="rotate(-90 50 50)"
          style={{ transition: 'stroke-dashoffset 0.5s ease' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
        <span style={{ fontSize: '1.5rem', fontWeight: 700, color }}>{score}%</span>
      </div>
    </div>
  );
}

function StatCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <Card padding="sm">
      <div style={{ textAlign: 'center', padding: '0.5rem' }}>
        <p style={{ fontSize: '1.5rem', fontWeight: 700 }}>{value}</p>
        <p style={{ fontSize: '0.75rem', opacity: 0.6, marginTop: '0.25rem' }}>{label}</p>
        {sub && <p style={{ fontSize: '0.65rem', opacity: 0.4, marginTop: '0.15rem' }}>{sub}</p>}
      </div>
    </Card>
  );
}

export default function ExecutionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id!;
  const { t } = useTranslation();
  const navigate = useNavigate();
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const [execution, setExecution] = useState<Execution | null>(null);
  const [stats, setStats] = useState<UnifiedStats | null>(null);
  const [isLoadingPage, setIsLoadingPage] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  const handleProgressCompleted = useCallback(
    async (summary: ExecutionSummary) => {
      try {
        const updated = await getExecution(id);
        setExecution(updated);
      } catch {
        setExecution((prev) => prev ? { ...prev, status: 'completed', summary } : prev);
      }
    }, [id]
  );
  const handleProgressFailed = useCallback((_error: string) => {
    setExecution((prev) => (prev ? { ...prev, status: 'failed' } : prev));
  }, []);

  const isInProgress = execution?.status === 'running' || execution?.status === 'pending';
  const { progress, wsConnected } = useExecutionProgress(id, {
    enabled: isInProgress, onCompleted: handleProgressCompleted, onFailed: handleProgressFailed,
  });

  useEffect(() => {
    if (!activeCompany) return;
    (async () => {
      setIsLoadingPage(true);
      try {
        const [exec, unifiedStats] = await Promise.all([
          getExecution(id),
          companyApi.get<UnifiedStats>('/unified-stats/'),
        ]);
        setExecution(exec);
        setStats(unifiedStats);
      } catch {
        setPageError(t('errors.unknown'));
      } finally {
        setIsLoadingPage(false);
      }
    })();
  }, [id, activeCompany, t]);

  if (isLoadingPage) return <div className={styles.loading}><Spinner size="lg" /></div>;
  if (pageError || !execution) return (
    <div className={styles.errorWrap}>
      <Alert variant="error">{pageError ?? t('errors.unknown')}</Alert>
      <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className={styles.iconSm} />} onClick={() => navigate('/executions')}>{t('common.back')}</Button>
    </div>
  );

  const isCompleted = execution.status === 'completed';
  const isFailed = execution.status === 'failed';

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.headerRow}>
        <div className={styles.headerLeft}>
          <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className={styles.iconSm} />} onClick={() => navigate('/executions')}>{t('common.back')}</Button>
          <div>
            <div className={styles.titleRow}>
              <h1 className={styles.title}>Résultats d'analyse</h1>
              <Badge variant={STATUS_VARIANT[execution.status]}>
                {t(`executions.status.${execution.status}`)}
              </Badge>
            </div>
            <p className={styles.subtitle}>
              Analyse du {formatDate(execution.dateFrom)} au {formatDate(execution.dateTo)}
            </p>
          </div>
        </div>
      </div>

      {/* Live progress */}
      {isInProgress && (
        <Card padding="md">
          <ExecutionProgressBar progress={progress} wsConnected={wsConnected} />
        </Card>
      )}

      {/* Failed */}
      {isFailed && (
        <Alert variant="error">{progress?.error ?? execution.errorMessage ?? t('errors.unknown')}</Alert>
      )}

      {/* Stats */}
      {isCompleted && stats && (
        <>
          {/* Main score */}
          <Card padding="md">
            <div style={{ display: 'flex', alignItems: 'center', gap: '2rem', flexWrap: 'wrap' }}>
              <ScoreCircle score={stats.averageScore} />
              <div style={{ flex: 1 }}>
                <p style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  Complétude des données
                </p>
                <p style={{ fontSize: '0.8rem', opacity: 0.6, lineHeight: 1.5 }}>
                  {stats.totalTransactions} transactions collectées depuis {Object.keys(stats.bySource).length} sources.
                  En moyenne, {stats.averageScore}% des champs comptables sont renseignés par transaction.
                </p>
              </div>
            </div>
          </Card>

          {/* KPI cards */}
          <div className={styles.summaryGrid}>
            <StatCard label="Transactions collectées" value={stats.totalTransactions} />
            <StatCard
              label="Multi-source"
              value={stats.clustered}
              sub={`confirmées par ${stats.completeClusters} rapprochements`}
            />
            <StatCard
              label="Catégorisées"
              value={stats.enriched}
              sub={`${stats.totalTransactions > 0 ? Math.round(stats.enriched * 100 / stats.totalTransactions) : 0}% classifiées PCG`}
            />
            <StatCard label="Sources connectées" value={Object.keys(stats.bySource).length} />
          </div>

          {/* Sources breakdown */}
          <Card padding="md">
            <p style={{ fontWeight: 600, marginBottom: '0.75rem' }}>Sources de données</p>
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              {Object.entries(stats.bySource).map(([source, count]) => (
                <div key={source} style={{
                  display: 'flex', alignItems: 'center', gap: '0.5rem',
                  padding: '0.5rem 0.75rem', borderRadius: '0.5rem',
                  background: 'rgba(255,255,255,0.05)',
                }}>
                  <span style={{
                    width: '10px', height: '10px', borderRadius: '50%',
                    background: SOURCE_COLORS[source] ?? '#6B7280',
                  }} />
                  <span style={{ fontSize: '0.8rem' }}>
                    {SOURCE_NAMES[source] ?? source}
                  </span>
                  <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>{count}</span>
                </div>
              ))}
            </div>
          </Card>

          {/* Link to transactions */}
          <Card padding="md">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <p style={{ fontWeight: 600, marginBottom: '0.25rem' }}>Rapport comptable détaillé</p>
                <p style={{ fontSize: '0.8rem', opacity: 0.6 }}>
                  Scoring par transaction, champs manquants, rapprochements
                </p>
              </div>
              <Link to="/transactions">
                <Button size="sm" leftIcon={<ArrowRight className={styles.iconSm} />}>
                  Voir les transactions
                </Button>
              </Link>
            </div>
          </Card>
        </>
      )}
    </div>
  );
}
