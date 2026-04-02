import { clsx } from 'clsx';
import styles from './reconciliation-gauge.module.css';

interface ReconciliationGaugeProps {
  rate: number; // 0–100
}

export function ReconciliationGauge({ rate }: ReconciliationGaugeProps) {
  const clampedRate = Math.min(100, Math.max(0, rate));

  const colorClass =
    clampedRate >= 80
      ? styles.colorGreen
      : clampedRate >= 60
      ? styles.colorAmber
      : styles.colorRed;

  const barFillClass =
    clampedRate >= 80
      ? styles.barFillGreen
      : clampedRate >= 60
      ? styles.barFillAmber
      : styles.barFillRed;

  const strokeColor =
    clampedRate >= 80 ? 'var(--chart-green)'
      : clampedRate >= 60 ? 'var(--chart-amber)'
      : 'var(--chart-red)';

  const label =
    clampedRate >= 80
      ? 'Excellent'
      : clampedRate >= 60
      ? 'Moyen'
      : 'Faible';

  return (
    <div className={styles.container}>
      {/* Circular indicator */}
      <div className={styles.circleWrap}>
        <svg className={styles.svg} viewBox="0 0 100 100">
          {/* Track */}
          <circle
            cx="50"
            cy="50"
            r="42"
            className={styles.track}
          />
          {/* Progress */}
          <circle
            cx="50"
            cy="50"
            r="42"
            fill="none"
            stroke={strokeColor}
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={`${(clampedRate / 100) * 263.9} 263.9`}
            className={styles.progress}
          />
        </svg>
        <div>
          <p className={clsx(styles.percentage, colorClass)}>{clampedRate}%</p>
        </div>
      </div>

      {/* Label + linear bar */}
      <div className={styles.barSection}>
        <div className={styles.barHeader}>
          <span className={styles.barLabel}>Taux de réconciliation</span>
          <span className={colorClass}>{label}</span>
        </div>
        <div className={styles.barTrack}>
          <div
            className={clsx(styles.barFill, barFillClass)}
            style={{ width: `${clampedRate}%` }}
          />
        </div>
        <div className={styles.barScale}>
          <span>0%</span>
          <span>50%</span>
          <span>100%</span>
        </div>
      </div>
    </div>
  );
}
