/**
 * Company-scoped API wrapper.
 *
 * Automatically prefixes all paths with `/companies/{activeCompanyId}`
 * so that hooks and components do not need to manually inject the company ID.
 *
 * IMPORTANT: The company ID comes from the Zustand store (URL path param),
 * never from the request body. This enforces multi-tenant isolation.
 */
import { apiClient } from './api-client';
import { useCompanyStore } from '@/stores/company-store';

function getActiveCompanyId(): string {
  const store = useCompanyStore.getState();
  const companyId = store.activeCompany?.publicId;
  if (!companyId) throw new Error('No active company selected');
  return companyId;
}

export const companyApi = {
  get: <T>(path: string, options?: Parameters<typeof apiClient.get>[1]) =>
    apiClient.get<T>(`/companies/${getActiveCompanyId()}${path}`, options),

  post: <T>(path: string, body?: unknown, options?: Parameters<typeof apiClient.post>[2]) =>
    apiClient.post<T>(`/companies/${getActiveCompanyId()}${path}`, body, options),

  patch: <T>(path: string, body?: unknown, options?: Parameters<typeof apiClient.patch>[2]) =>
    apiClient.patch<T>(`/companies/${getActiveCompanyId()}${path}`, body, options),

  put: <T>(path: string, body?: unknown, options?: Parameters<typeof apiClient.put>[2]) =>
    apiClient.put<T>(`/companies/${getActiveCompanyId()}${path}`, body, options),

  delete: <T>(path: string, options?: Parameters<typeof apiClient.delete>[1]) =>
    apiClient.delete<T>(`/companies/${getActiveCompanyId()}${path}`, options),
};
