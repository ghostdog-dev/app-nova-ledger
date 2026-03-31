import { useState, useCallback, useEffect } from 'react';
import { companyApi } from '@/lib/company-api';
import { useCompanyStore } from '@/stores/company-store';
import type { ServiceConnection, PaginatedResponse } from '@/types';

// -- API functions ---------------------------------------------------------------

/**
 * Fetch all service connections for the active company.
 * Backend endpoint: GET /companies/{company_pk}/connections/
 */
export async function getConnections(): Promise<ServiceConnection[]> {
  const data = await companyApi.get<PaginatedResponse<ServiceConnection>>('/connections/');
  return data.results;
}

/**
 * Initiate OAuth flow for a given provider.
 * Backend endpoint: POST /companies/{company_pk}/connections/oauth/initiate/
 */
export async function initiateOAuth(
  providerName: string,
  redirectUri: string
): Promise<{ authorizationUrl: string }> {
  return companyApi.post<{ authorizationUrl: string }>(
    '/connections/oauth/initiate/',
    { providerName, redirectUri }
  );
}

/**
 * Complete an OAuth flow after receiving the callback.
 * Backend endpoint: POST /companies/{company_pk}/connections/oauth/complete/
 */
export async function completeOAuth(data: {
  providerName: string;
  code: string;
  state: string;
  redirectUri: string;
}): Promise<ServiceConnection> {
  return companyApi.post<ServiceConnection>('/connections/oauth/complete/', data);
}

/**
 * Connect via API key (non-OAuth providers).
 * Backend endpoint: POST /companies/{company_pk}/connections/
 */
export async function connectApiKey(
  providerName: string,
  serviceType: string,
  credentials: Record<string, string> | string
): Promise<ServiceConnection> {
  const creds = typeof credentials === 'string'
    ? { api_key: credentials }
    : credentials;
  return companyApi.post<ServiceConnection>('/connections/', {
    serviceType,
    providerName,
    authType: 'api_key',
    credentials: creds,
  });
}

/**
 * Test whether a connection is still active.
 * Backend endpoint: POST /companies/{company_pk}/connections/{id}/check/
 */
export async function checkConnection(id: string): Promise<{ ok: boolean; error?: string }> {
  return companyApi.post<{ ok: boolean; error?: string }>(`/connections/${id}/check/`);
}

/**
 * Disconnect and delete a service connection.
 * Backend endpoint: DELETE /companies/{company_pk}/connections/{id}/
 */
export async function deleteConnection(id: string): Promise<void> {
  return companyApi.delete<void>(`/connections/${id}/`);
}

// -- Hook ------------------------------------------------------------------------

interface UseConnectionsReturn {
  connections: ServiceConnection[];
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
  disconnect: (id: string) => Promise<void>;
  test: (id: string) => Promise<boolean>;
}

/**
 * Hook that manages the full lifecycle of service connections.
 * Fetches on mount and provides mutation helpers with optimistic updates.
 */
export function useConnections(): UseConnectionsReturn {
  const activeCompany = useCompanyStore((s) => s.activeCompany);
  const [connections, setConnections] = useState<ServiceConnection[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchConnections = useCallback(async () => {
    if (!activeCompany) return;
    setIsLoading(true);
    setError(null);
    try {
      const data = await getConnections();
      setConnections(data);
    } catch (err) {
      const msg = (err as { message?: string })?.message ?? 'Failed to load connections';
      setError(msg);
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  const disconnect = useCallback(async (id: string) => {
    // Optimistic remove
    setConnections((prev) => prev.filter((c) => c.publicId !== id));
    try {
      await deleteConnection(id);
    } catch {
      // Rollback on failure -- refetch from server
      await fetchConnections();
      throw new Error('Failed to disconnect service');
    }
  }, [fetchConnections]);

  const test = useCallback(async (id: string): Promise<boolean> => {
    const result = await checkConnection(id);
    return result.ok;
  }, []);

  return {
    connections,
    isLoading,
    error,
    refetch: fetchConnections,
    disconnect,
    test,
  };
}
