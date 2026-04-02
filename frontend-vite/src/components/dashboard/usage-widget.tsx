import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Zap, Plug, Users } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { useCompanyStore } from '@/stores/company-store';
import styles from './usage-widget.module.css';
import { Link } from 'react-router-dom';

interface CircularProgressProps {
  value: number;   // 0–100 percent
  size?: number;
  strokeWidth?: number;
  label: string;
  current: number;
  limit: number | null;
  icon: React.ReactNode;
}

function CircularProgress({ value, size = 80, strokeWidth = 7, label, current, limit, icon }: CircularProgressProps) {
  const clamped = Math.min(100, Math.max(0, value));
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (clamped / 100) * circumference;

  const color =
    clamped >= 90 ? 'var(--chart-red)'
      : clamped >= 70 ? 'var(--chart-amber)'
      : 'var(--chart-green)';

  return (
    <div className={styles.gauge}>
      <div className={styles.gaugeCircle} style={{ width: size, height: size }}>
        <svg width={size} height={size} className={styles.gaugeSvg}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            className={styles.gaugeTrack}
            strokeWidth={strokeWidth}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={styles.transitionAll}
          />
        </svg>
        <div className={styles.gaugeIcon}>
          <span>{icon}</span>
        </div>
      </div>
      <div className={styles.gaugeLabel}>
        <p className={styles.gaugeCurrent}>
          {current}
          {limit !== null && <span className={styles.gaugeLimit}> / {limit}</span>}
        </p>
        <p className={styles.gaugeName}>{label}</p>
      </div>
    </div>
  );
}

export function UsageWidget() {
  const { t } = useTranslation();
  const { usage, activeCompany, fetchUsage } = useCompanyStore();

  useEffect(() => {
    if (activeCompany) fetchUsage();
  }, [activeCompany, fetchUsage]);

  const pct = (current: number, limit: number | null) =>
    limit === null ? 0 : Math.round((current / limit) * 100);

  const execCurrent = usage?.executionsThisMonth ?? 0;
  const execLimit = usage?.limits?.executionsPerMonth ?? null;
  const connCurrent = usage?.connections ?? 0;
  const connLimit = usage?.limits?.connections ?? null;
  const membCurrent = usage?.members ?? 0;
  const membLimit = usage?.limits?.members ?? null;

  return (
    <Card padding="md">
      <CardHeader>
        <div className={styles.headerRow}>
          <CardTitle>{t('usage.title')}</CardTitle>
          <Link to="/settings/plans"
            className={styles.plansLink}
          >
            {t('usage.seeAllPlans')} →
          </Link>
        </div>
      </CardHeader>
      <CardContent>
        <div className={styles.gaugesRow}>
          <CircularProgress
            value={pct(execCurrent, execLimit)}
            current={execCurrent}
            limit={execLimit}
            label={t('usage.executions')}
            icon={<Zap className={styles.iconSm} />}
          />
          <CircularProgress
            value={pct(connCurrent, connLimit)}
            current={connCurrent}
            limit={connLimit}
            label={t('usage.connections')}
            icon={<Plug className={styles.iconSm} />}
          />
          <CircularProgress
            value={pct(membCurrent, membLimit)}
            current={membCurrent}
            limit={membLimit}
            label={t('usage.members')}
            icon={<Users className={styles.iconSm} />}
          />
        </div>
      </CardContent>
    </Card>
  );
}
