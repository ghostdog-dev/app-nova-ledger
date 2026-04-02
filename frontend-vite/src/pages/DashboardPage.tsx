import { useState, useEffect, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Database, TrendingUp, Layers, Link2, Loader2, Building2, Plus,
  ArrowUpRight, ArrowDownRight, Zap,
} from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { AddConnectionModal } from '@/components/connections/add-connection-modal';
import { companyApi } from '@/lib/company-api';
import { useCompanyStore } from '@/stores/company-store';
import styles from './DashboardPage.module.css';
import { useNavigate, Link } from 'react-router-dom';

// ── Types ───────────────────────────────────────────────────────────────────

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
  bank_api: 'Banque API', bankApi: 'Banque API',
  bank_import: 'Import fichier', bankImport: 'Import fichier',
  email: 'Email',
};
const SOURCE_COLORS: Record<string, string> = {
  stripe: '#635BFF', mollie: '#FF6B6B', paypal: '#0070BA',
  bank_api: '#10B981', bankApi: '#10B981',
  bank_import: '#6366F1', bankImport: '#6366F1',
  email: '#8B5CF6',
};

function scoreColor(score: number): string {
  if (score >= 80) return '#10B981';
  if (score >= 40) return '#F59E0B';
  return '#EF4444';
}

// ── Components ──────────────────────────────────────────────────────────────

function KpiCard({ label, value, sub, icon, color }: {
  label: string; value: string | number; sub?: string;
  icon: React.ReactNode; color?: string;
}) {
  return (
    <Card padding="md">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <p style={{ fontSize: '0.75rem', opacity: 0.5, marginBottom: '0.25rem' }}>{label}</p>
          <p style={{ fontSize: '1.75rem', fontWeight: 700, color: color ?? 'inherit' }}>{value}</p>
          {sub && <p style={{ fontSize: '0.7rem', opacity: 0.4, marginTop: '0.15rem' }}>{sub}</p>}
        </div>
        <span style={{ opacity: 0.3 }}>{icon}</span>
      </div>
    </Card>
  );
}

function ScoreRing({ score }: { score: number }) {
  const color = scoreColor(score);
  const size = 120;
  const r = 48;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  return (
    <div style={{ position: 'relative', width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="10" />
        <circle cx={size/2} cy={size/2} r={r} fill="none" stroke={color} strokeWidth="10"
          strokeDasharray={circ} strokeDashoffset={offset} strokeLinecap="round"
          transform={`rotate(-90 ${size/2} ${size/2})`} style={{ transition: 'stroke-dashoffset 0.6s ease' }} />
      </svg>
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column' }}>
        <span style={{ fontSize: '1.75rem', fontWeight: 700, color }}>{score}%</span>
        <span style={{ fontSize: '0.6rem', opacity: 0.4 }}>complétude</span>
      </div>
    </div>
  );
}

function SourceBar({ name, count, total, color }: { name: string; count: number; total: number; color: string }) {
  const pct = total > 0 ? Math.round(count * 100 / total) : 0;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.5rem' }}>
      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: color, flexShrink: 0 }} />
      <span style={{ fontSize: '0.8rem', flex: 1 }}>{name}</span>
      <span style={{ fontSize: '0.8rem', fontWeight: 600, minWidth: '2rem', textAlign: 'right' }}>{count}</span>
      <div style={{ width: '60px', height: '4px', borderRadius: '2px', background: 'rgba(255,255,255,0.06)' }}>
        <div style={{ width: `${pct}%`, height: '100%', borderRadius: '2px', background: color, transition: 'width 0.3s' }} />
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const activeCompany = useCompanyStore((s) => s.activeCompany);
  const [addModalOpen, setAddModalOpen] = useState(false);

  const [stats, setStats] = useState<UnifiedStats | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchStats = useCallback(async () => {
    if (!activeCompany) {
      setError('NO_COMPANY');
      setIsLoading(false);
      return;
    }
    try {
      const data = await companyApi.get<UnifiedStats>('/unified-stats/');
      setStats(data);
    } catch {
      setError('Erreur de chargement');
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany]);

  useEffect(() => { fetchStats(); }, [fetchStats]);

  if (isLoading) {
    return (
      <div className={styles.loadingState}>
        <Loader2 className={styles.spinner} />
        <p>Chargement...</p>
      </div>
    );
  }

  if (error === 'NO_COMPANY') {
    return (
      <div className={styles.errorState}>
        <Building2 className={styles.iconMd} />
        <h2 style={{ margin: '0.5rem 0', fontSize: '1.25rem' }}>{t('dashboard.noCompanyTitle')}</h2>
        <p style={{ marginBottom: '1rem', opacity: 0.7 }}>{t('dashboard.noCompanyMessage')}</p>
        <button type="button" onClick={() => navigate('/settings/company?create=1')}
          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.625rem 1.25rem', borderRadius: '0.5rem', background: 'var(--color-accent, #1C1C1C)', color: 'var(--color-bg, #fff)', border: 'none', cursor: 'pointer', fontSize: '0.875rem', fontWeight: 500 }}>
          <Plus size={16} /> {t('dashboard.createCompany')}
        </button>
      </div>
    );
  }

  if (error || !stats) {
    return <div className={styles.errorState}><p>{error}</p></div>;
  }

  const sourceEntries = Object.entries(stats.bySource);
  const totalSources = sourceEntries.length;
  const hasData = stats.totalTransactions > 0;

  return (
    <>
      <div>
        <div className={styles.pageHeader}>
          <h1 className={styles.title}>Tableau de bord</h1>
          <p className={styles.subtitle}>
            {hasData
              ? `${stats.totalTransactions} transactions depuis ${totalSources} source${totalSources > 1 ? 's' : ''}`
              : 'Connectez vos services pour commencer'}
          </p>
        </div>

        {!hasData ? (
          /* Empty state */
          <Card padding="md">
            <div style={{ textAlign: 'center', padding: '2rem' }}>
              <Database size={40} style={{ opacity: 0.2, marginBottom: '1rem' }} />
              <p style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '0.5rem' }}>Aucune donnée</p>
              <p style={{ fontSize: '0.85rem', opacity: 0.5, marginBottom: '1.5rem' }}>
                Connectez vos services (Stripe, email, banque...) puis lancez une analyse.
              </p>
              <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'center' }}>
                <Button size="sm" leftIcon={<Link2 size={14} />} onClick={() => setAddModalOpen(true)}>
                  Connecter un service
                </Button>
                <Button size="sm" variant="secondary" leftIcon={<Zap size={14} />} onClick={() => navigate('/executions/new')}>
                  Lancer une analyse
                </Button>
              </div>
            </div>
          </Card>
        ) : (
          <>
            {/* KPIs */}
            <div className={styles.section}>
              <div className={styles.kpiGrid}>
                <KpiCard
                  label="Transactions collectées"
                  value={stats.totalTransactions}
                  icon={<Database size={20} />}
                />
                <KpiCard
                  label="Multi-source"
                  value={stats.clustered}
                  sub={`${stats.completeClusters} rapprochements confirmés`}
                  icon={<Layers size={20} />}
                />
                <KpiCard
                  label="Catégorisées"
                  value={stats.enriched}
                  sub={`${stats.totalTransactions > 0 ? Math.round(stats.enriched * 100 / stats.totalTransactions) : 0}% classifiées`}
                  icon={<TrendingUp size={20} />}
                />
                <KpiCard
                  label="Sources"
                  value={totalSources}
                  icon={<Link2 size={20} />}
                />
              </div>
            </div>

            {/* Main grid */}
            <div className={styles.section}>
              <div className={styles.chartsRow}>
                {/* Completeness ring */}
                <Card padding="md">
                  <CardHeader>
                    <CardTitle className={styles.chartTitle}>Complétude moyenne</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '1rem 0' }}>
                      <ScoreRing score={stats.averageScore} />
                    </div>
                    <p style={{ textAlign: 'center', fontSize: '0.75rem', opacity: 0.4 }}>
                      Sur 6 champs : montant, date, fournisseur, catégorie, multi-source, TVA
                    </p>
                  </CardContent>
                </Card>

                {/* Sources breakdown */}
                <Card padding="md" className={styles.chartsRowWide}>
                  <CardHeader>
                    <CardTitle className={styles.chartTitle}>Répartition par source</CardTitle>
                  </CardHeader>
                  <CardContent>
                    <div style={{ padding: '0.5rem 0' }}>
                      {sourceEntries
                        .sort(([, a], [, b]) => b - a)
                        .map(([source, count]) => (
                          <SourceBar
                            key={source}
                            name={SOURCE_NAMES[source] ?? source}
                            count={count}
                            total={stats.totalTransactions}
                            color={SOURCE_COLORS[source] ?? '#6B7280'}
                          />
                        ))}
                    </div>
                  </CardContent>
                </Card>
              </div>
            </div>

            {/* Quick actions */}
            <div className={styles.section}>
              <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap' }}>
                <Link to="/transactions">
                  <Button size="sm" variant="secondary" leftIcon={<ArrowUpRight size={14} />}>
                    Voir les transactions
                  </Button>
                </Link>
                <Link to="/executions/new">
                  <Button size="sm" variant="secondary" leftIcon={<Zap size={14} />}>
                    Lancer une analyse
                  </Button>
                </Link>
                <Button size="sm" variant="secondary" leftIcon={<Link2 size={14} />} onClick={() => setAddModalOpen(true)}>
                  Ajouter une source
                </Button>
              </div>
            </div>
          </>
        )}
      </div>

      <AddConnectionModal
        open={addModalOpen}
        onClose={() => setAddModalOpen(false)}
        onSuccess={() => { setAddModalOpen(false); fetchStats(); }}
      />
    </>
  );
}
