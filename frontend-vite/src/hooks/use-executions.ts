import { useState, useCallback, useEffect } from 'react';
import { companyApi } from '@/lib/company-api';
import { apiClient } from '@/lib/api-client';
import { useCompanyStore } from '@/stores/company-store';
import type {
  Execution,
  Correlation,
  CreateExecutionPayload,
  CorrelationUpdatePayload,
  ExportFile,
  PaginatedResponse,
} from '@/types';

// -- API functions ---------------------------------------------------------------

/**
 * Fetch all executions for the active company.
 * Backend endpoint: GET /companies/{company_pk}/executions/
 */
export async function getExecutions(): Promise<Execution[]> {
  const data = await companyApi.get<PaginatedResponse<Execution>>('/executions/');
  return data.results;
}

/**
 * Fetch a single execution.
 * Backend endpoint: GET /companies/{company_pk}/executions/{id}/
 */
export async function getExecution(id: string | number): Promise<Execution> {
  return companyApi.get<Execution>(`/executions/${id}/`);
}

/**
 * Create a new execution.
 * Backend endpoint: POST /companies/{company_pk}/executions/
 */
export async function createExecution(data: CreateExecutionPayload): Promise<Execution> {
  return companyApi.post<Execution>('/executions/', data);
}

/**
 * Fetch correlations for an execution.
 * Backend endpoint: GET /correlations/?execution={id}  (top-level, not nested)
 */
export async function getCorrelations(executionId: string | number): Promise<Correlation[]> {
  const data = await apiClient.get<PaginatedResponse<Correlation>>(
    `/correlations/?execution=${executionId}`
  );
  return data.results;
}

/**
 * Patch a correlation (manual override).
 * Backend endpoint: PATCH /correlations/{cid}/  (top-level)
 */
export async function patchCorrelation(
  correlationId: string | number,
  patch: CorrelationUpdatePayload
): Promise<Correlation> {
  return apiClient.patch<Correlation>(`/correlations/${correlationId}/`, patch);
}

/**
 * Request an export for an execution.
 * Backend endpoint: POST /companies/{company_pk}/executions/{id}/exports/
 * Returns the ExportFile object (status will be 'pending' initially).
 */
export async function requestExport(
  executionId: string | number,
  format: string
): Promise<ExportFile> {
  return companyApi.post<ExportFile>(`/executions/${executionId}/exports/`, { format });
}

// -- Hook ------------------------------------------------------------------------

interface UseExecutionsReturn {
  executions: Execution[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useExecutions(): UseExecutionsReturn {
  const activeCompany = useCompanyStore((s) => s.activeCompany);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchExecutions = useCallback(async () => {
    if (!activeCompany) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getExecutions();
      setExecutions(data);
    } catch (err) {
      const msg = (err as { message?: string })?.message ?? 'Failed to load executions';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany]);

  useEffect(() => {
    fetchExecutions();
  }, [fetchExecutions]);

  return { executions, isLoading, error, refetch: fetchExecutions };
}
