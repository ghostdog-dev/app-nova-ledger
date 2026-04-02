import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import styles from './monthly-evolution-chart.module.css';

export interface MonthlyData {
  month: string; // e.g. "Jan", "Fev"
  correlations: number;
  anomalies: number;
}

interface MonthlyEvolutionChartProps {
  data: MonthlyData[];
}

export function MonthlyEvolutionChart({ data }: MonthlyEvolutionChartProps) {
  if (data.length === 0) {
    return (
      <div className={styles.empty}>
        Aucune donnee disponible
      </div>
    );
  }

  return (
    <div className={styles.chartContainer}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 4, right: 4, left: -16, bottom: 0 }} barSize={16} barCategoryGap="30%">
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" vertical={false} />
          <XAxis
            dataKey="month"
            tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={{ fontSize: 11, fill: 'var(--chart-axis)' }}
            axisLine={false}
            tickLine={false}
            allowDecimals={false}
          />
          <Tooltip
            contentStyle={{
              borderRadius: 0,
              border: '1px solid var(--chart-tooltip-border)',
              backgroundColor: 'var(--chart-tooltip-bg)',
              color: 'var(--color-text)',
              fontFamily: 'var(--font-mono)',
              fontSize: '12px',
            }}
            cursor={{ fill: 'var(--chart-cursor)' }}
          />
          <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: '11px', fontFamily: 'var(--font-mono)' }} />
          <Bar dataKey="correlations" name="Correlations" fill="var(--chart-blue)" radius={[0, 0, 0, 0]} />
          <Bar dataKey="anomalies" name="Anomalies" fill="var(--chart-amber)" radius={[0, 0, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
