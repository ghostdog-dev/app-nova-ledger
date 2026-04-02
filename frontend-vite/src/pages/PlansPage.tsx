import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Check, Zap, Plug, Users, TrendingUp } from 'lucide-react';
import { clsx } from 'clsx';
import { Card } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useCompanyStore } from '@/stores/company-store';
import { useAuthStore } from '@/stores/auth-store';
import { apiClient } from '@/lib/api-client';
import type { PlanType } from '@/types';
import styles from './PlansPage.module.css';

interface PlanSpec {
  id: PlanType;
  priceId: string;
  price: string;
  executions: string;
  connections: string;
  members: string;
  features: string[];
  highlighted?: boolean;
}

const DEFAULT_PLANS: PlanSpec[] = [
  {
    id: 'free',
    priceId: 'free',
    price: '\u20AC0',
    executions: '5 / mois',
    connections: '2',
    members: '1',
    features: [
      'Export CSV',
      'R\u00e9conciliation facture \u2194 paiement',
      'Historique 30 jours',
    ],
  },
  {
    id: 'plan1',
    priceId: '',
    price: '\u20AC29',
    executions: '50 / mois',
    connections: '5',
    members: '5',
    features: [
      'Tout du Free',
      'Export Excel, PDF, JSON',
      'Three-way matching',
      'Historique illimit\u00e9',
      'Notifications email',
    ],
    highlighted: true,
  },
  {
    id: 'plan2',
    priceId: '',
    price: '\u20AC99',
    executions: 'Illimit\u00e9',
    connections: 'Illimit\u00e9',
    members: 'Illimit\u00e9',
    features: [
      'Tout du Plan 1',
      'Matching ligne par ligne',
      'Multi-entreprise',
      'Assistant IA avanc\u00e9',
      'Support prioritaire',
    ],
  },
];

function UsageBar({ label, current, limit, icon }: { label: string; current: number; limit: number | null; icon: React.ReactNode }) {
  const pct = limit === null ? 0 : Math.min(100, Math.round((current / limit) * 100));
  const barClass = pct >= 90 ? styles.usageBarDanger : pct >= 70 ? styles.usageBarWarning : styles.usageBarNormal;

  return (
    <div className={styles.usageItem}>
      <div className={styles.usageHeader}>
        <span className={styles.usageLabelWrap}>
          {icon}
          {label}
        </span>
        <span className={styles.usageValue}>
          {current}{limit !== null && ` / ${limit}`}
          {limit === null && ' (illimit\u00e9)'}
        </span>
      </div>
      {limit !== null && (
        <div className={styles.usageBarTrack}>
          <div
            className={clsx(styles.usageBarFill, barClass)}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </div>
  );
}

export default function PlansPage() {
  const { t } = useTranslation();
  const { activeCompany, plan, usage, fetchPlan, fetchUsage } = useCompanyStore();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [plans, setPlans] = useState<PlanSpec[]>(DEFAULT_PLANS);

  useEffect(() => {
    if (activeCompany) {
      fetchPlan();
      fetchUsage();
    }
  }, [activeCompany, fetchPlan, fetchUsage]);

  useEffect(() => {
    apiClient.get<{ plans: { id: string; price_id: string | null }[] }>('/billing/plans/')
      .then((data) => {
        const priceMap = new Map(data.plans.map((p) => [p.id, p.price_id]));
        setPlans(DEFAULT_PLANS.map((p) => ({
          ...p,
          priceId: priceMap.get(p.id) ?? p.priceId,
        })));
      })
      .catch(() => { /* keep defaults */ });
  }, []);

  const { user } = useAuthStore();
  const currentPlan = plan?.plan ?? activeCompany?.plan ?? 'free';
  const isOwner = activeCompany?.owner?.id === user?.id;

  const handleChangePlan = async (priceId: string) => {
    if (!isOwner) return;
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.post<{ url: string }>('/billing/checkout-session/', {
        price_id: priceId,
      });
      window.location.href = response.url;
    } catch {
      setError(t('plans.error', 'Erreur lors du changement de plan'));
    } finally {
      setLoading(false);
    }
  };

  const handleManageSubscription = async () => {
    setError(null);
    try {
      const response = await apiClient.post<{ url: string }>('/billing/portal-session/');
      window.location.href = response.url;
    } catch {
      setError(t('plans.portalError', "Erreur lors de l'ouverture du portail"));
    }
  };

  return (
    <div className={styles.page}>
      {/* Header */}
      <div>
        <h1 className={styles.title}>{t('plans.title')}</h1>
        <p className={styles.subtitle}>{t('plans.subtitle')}</p>
      </div>

      {error && (
        <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>
      )}

      {!isOwner && (
        <Alert variant="info">Seul le propri\u00e9taire de l&apos;entreprise peut changer de plan.</Alert>
      )}

      {/* Pricing cards */}
      <div className={styles.planGrid}>
        {plans.map((p) => {
          const isCurrent = p.id === currentPlan;
          const isUpgrade = ['free', 'plan1', 'plan2'].indexOf(p.id) > ['free', 'plan1', 'plan2'].indexOf(currentPlan);

          return (
            <Card
              key={p.id}
              padding="none"
              className={clsx(
                styles.planCard,
                p.highlighted && styles.planHighlighted,
                isCurrent && styles.planCurrent
              )}
            >
              {/* Card header */}
              <div className={clsx(
                styles.planHeader,
                p.highlighted && styles.planHeaderHighlighted
              )}>
                {p.highlighted && (
                  <p className={styles.popularLabel}>
                    Populaire
                  </p>
                )}
                <div className={styles.planNameRow}>
                  <h2 className={clsx(styles.planName, p.highlighted && styles.planNameLight)}>
                    {t(`plans.${p.id}.name`)}
                  </h2>
                  {isCurrent && (
                    <span className={styles.currentBadge}>
                      {t('plans.current')}
                    </span>
                  )}
                </div>
                <div className={styles.priceRow}>
                  <span className={clsx(styles.price, p.highlighted && styles.priceLight)}>
                    {p.price}
                  </span>
                  <span className={clsx(styles.pricePeriod, p.highlighted && styles.pricePeriodLight)}>
                    /mois
                  </span>
                </div>
              </div>

              {/* Limits */}
              <div className={styles.limitsSection}>
                <div className={styles.limitRow}>
                  <Zap className={styles.limitIcon} />
                  <span>{p.executions} analyses</span>
                </div>
                <div className={styles.limitRow}>
                  <Plug className={styles.limitIcon} />
                  <span>{p.connections} connexions</span>
                </div>
                <div className={styles.limitRow}>
                  <Users className={styles.limitIcon} />
                  <span>{p.members} membre{p.members !== '1' ? 's' : ''}</span>
                </div>
              </div>

              {/* Features */}
              <div className={styles.featuresSection}>
                {p.features.map((f) => (
                  <div key={f} className={styles.featureRow}>
                    <Check className={styles.featureCheck} />
                    {f}
                  </div>
                ))}
              </div>

              {/* CTA */}
              <div className={styles.ctaSection}>
                {isCurrent ? (
                  p.id === 'free' ? (
                    <Button variant="secondary" size="sm" fullWidth disabled>
                      {t('plans.current')}
                    </Button>
                  ) : (
                    <Button
                      variant="secondary"
                      size="sm"
                      fullWidth
                      disabled={!isOwner}
                      onClick={handleManageSubscription}
                    >
                      {t('plans.manageSubscription', 'G\u00e9rer l\u2019abonnement')}
                    </Button>
                  )
                ) : (
                  <Button
                    variant={isUpgrade ? 'primary' : 'secondary'}
                    size="sm"
                    fullWidth
                    isLoading={loading}
                    disabled={!isOwner || loading}
                    onClick={() => handleChangePlan(p.priceId)}
                    leftIcon={isUpgrade ? <TrendingUp className={styles.trendIcon} /> : undefined}
                  >
                    {isUpgrade ? t('plans.upgrade') : t('plans.downgrade')}
                  </Button>
                )}
              </div>
            </Card>
          );
        })}
      </div>

      {/* Usage section */}
      {usage && (
        <Card padding="md">
          <h2 className={styles.usageTitle}>
            {t('usage.title')}
          </h2>
          <div className={styles.usageList}>
            <UsageBar
              label={t('usage.executions')}
              current={usage.executionsThisMonth}
              limit={usage.limits.executionsPerMonth ?? null}
              icon={<Zap className={styles.usageIcon} />}
            />
            <UsageBar
              label={t('usage.connections')}
              current={usage.connections}
              limit={usage.limits.connections ?? null}
              icon={<Plug className={styles.usageIcon} />}
            />
            <UsageBar
              label={t('usage.members')}
              current={usage.members}
              limit={usage.limits.members ?? null}
              icon={<Users className={styles.usageIcon} />}
            />
          </div>
        </Card>
      )}

      {!usage && <div className={styles.loadingCenter}><Spinner size="sm" /></div>}
    </div>
  );
}
