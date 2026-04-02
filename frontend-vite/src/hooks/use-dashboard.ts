import { useState, useCallback, useEffect } from 'react';
import { companyApi } from '@/lib/company-api';
import { useCompanyStore } from '@/stores/company-store';
import type { ServiceConnection, Execution } from '@/types';
import type { DashboardAlert } from '@/components/dashboard/alerts-widget';
import type { MonthlyData } from '@/components/dashboard/monthly-evolution-chart';

// ── Types ────────────────────────────────────────────────────────────────────

export interface DashboardStats {
  reconciliationRate: number;
  totalInvoices: number;
  anomalies: number;
  connectedServices: number;
}

export interface CorrelationDistributionItem {
  status: string;
  count: number;
}

export interface Transaction {
  date: string;
  desc: string;
  amount: string;
  status: 'matched' | 'pending' | 'orphan';
  source: string;
}

export interface RecentTransactions {
  transactions: Transaction[];
  totalCount: number;
}

export interface DashboardData {
  stats: DashboardStats;
  correlationDistribution: CorrelationDistributionItem[];
  monthlyEvolution: MonthlyData[];
  alerts: DashboardAlert[];
  lastExecution: Execution | null;
  recentTransactions: RecentTransactions;
  connections: ServiceConnection[];
}

// ── Hook ─────────────────────────────────────────────────────────────────────

interface UseDashboardReturn {
  data: DashboardData | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

/**
 * Fetches all dashboard data in a single API call.
 * Backend endpoint: GET /companies/{company_pk}/dashboard/
 */
export function useDashboard(): UseDashboardReturn {
  const [data, setData] = useState<DashboardData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const fetchDashboard = useCallback(async () => {
    if (!activeCompany) {
      setIsLoading(false);
      setError('NO_COMPANY');
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const result = await companyApi.get<DashboardData>('/dashboard/');
      setData(result);
    } catch (err) {
      const msg = (err as { message?: string })?.message ?? 'Failed to load dashboard data';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany]);

  useEffect(() => {
    fetchDashboard();
  }, [fetchDashboard]);

  return { data, isLoading, error, refetch: fetchDashboard };
}
