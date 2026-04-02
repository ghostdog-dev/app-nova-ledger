import { PieChart, Pie, Cell, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import { useTranslation } from 'react-i18next';
import styles from './correlation-status-chart.module.css';

interface StatusData {
  status: string;
  count: number;
}

interface CorrelationStatusChartProps {
  data: StatusData[];
}

// Read CSS custom properties at runtime so they adapt to light/dark theme
function getChartVar(name: string, fallback: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
}

function getStatusColors(): Record<string, string> {
  return {
    reconciled: getChartVar('--chart-green', '#3D7A6E'),
    reconciled_with_alert: getChartVar('--chart-amber', '#C47A32'),
    alert: getChartVar('--chart-amber', '#C47A32'),
    unpaid: getChartVar('--chart-red', '#9B3A3A'),
    unreconciled: getChartVar('--chart-red', '#9B3A3A'),
    orphan_payment: getChartVar('--chart-orange', '#B8652A'),
    uncertain: getChartVar('--chart-muted', '#8A857D'),
  };
}

export function CorrelationStatusChart({ data }: CorrelationStatusChartProps) {
  const { t } = useTranslation();

  const STATUS_COLORS = getStatusColors();
  const chartData = data.map((d) => ({
    name: t(`executions.correlationStatus.${d.status}` as Parameters<typeof t>[0]),
    value: d.count,
    color: STATUS_COLORS[d.status] ?? getChartVar('--chart-muted', '#8A857D'),
  }));

  const total = data.reduce((s, d) => s + d.count, 0);

  if (total === 0) {
    return (
      <div className={styles.empty}>
        Aucune donnee disponible
      </div>
    );
  }

  return (
    <div className={styles.wrapper}>
      {/* Pie + Legend rendered by Recharts */}
      <div className={styles.chartContainer}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={chartData}
              cx="50%"
              cy="50%"
              innerRadius={52}
              outerRadius={72}
              paddingAngle={2}
              dataKey="value"
            >
              {chartData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} stroke="transparent" />
              ))}
            </Pie>
            <Tooltip
              formatter={(value: number | undefined) => [value ?? 0, '']}
              contentStyle={{
                borderRadius: 0,
                border: '1px solid var(--chart-tooltip-border)',
                backgroundColor: 'var(--chart-tooltip-bg)',
                color: 'var(--color-text)',
                fontFamily: 'var(--font-mono)',
                fontSize: '12px',
              }}
            />
          </PieChart>
        </ResponsiveContainer>
        {/* Center label — HTML overlay, centered on the pie area */}
        <div className={styles.centerLabel}>
          <p className={styles.total}>{total}</p>
          <p className={styles.totalLabel}>correlations</p>
        </div>
      </div>
      {/* Legend below, outside the pie area */}
      <div className={styles.legendContainer}>
        {chartData.map((entry, index) => (
          <span key={index} className={styles.legendItem}>
            <span className={styles.legendDot} style={{ backgroundColor: entry.color }} />
            {entry.name}
          </span>
        ))}
      </div>
    </div>
  );
}
