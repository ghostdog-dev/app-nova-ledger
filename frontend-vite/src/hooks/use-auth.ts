import { useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { useCompanyStore } from '@/stores/company-store';
import { apiClient } from '@/lib/api-client';
import type { AuthResponse, LoginRequest, RegisterRequest } from '@/types';

/**
 * F01 — Validate that a redirect target is a safe same-origin relative path.
 * Rejects absolute URLs, protocol-relative URLs (//evil.com), and non-path strings.
 */
function isSafeRedirect(path: string): boolean {
  return path.startsWith('/') && !path.startsWith('//');
}

export function useAuth() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { user, isAuthenticated, isLoading, setAuth, clearAuth, setLoading } = useAuthStore();

  const login = useCallback(
    async (credentials: LoginRequest): Promise<void> => {
      setLoading(true);
      try {
        const response = await apiClient.post<AuthResponse>('/accounts/login/', credentials);
        setAuth(response.user, response.tokens.accessToken);
        await useCompanyStore.getState().fetchCompanies();

        const next = searchParams.get('next');
        if (next && isSafeRedirect(next)) {
          navigate(next);
        } else {
          navigate('/dashboard');
        }
      } finally {
        setLoading(false);
      }
    },
    [setAuth, setLoading, navigate, searchParams]
  );

  const register = useCallback(
    async (data: RegisterRequest): Promise<void> => {
      setLoading(true);
      try {
        const response = await apiClient.post<AuthResponse>('/accounts/register/', data);
        setAuth(response.user, response.tokens.accessToken);
        await useCompanyStore.getState().fetchCompanies();
        navigate('/dashboard');
      } finally {
        setLoading(false);
      }
    },
    [setAuth, setLoading, navigate]
  );

  const logout = useCallback(async (): Promise<void> => {
    try {
      // Backend reads refresh token from httpOnly cookie automatically
      await apiClient.post('/accounts/logout/');
    } catch {
      // Ignore errors on logout
    } finally {
      clearAuth();
      navigate('/login');
    }
  }, [clearAuth, navigate]);

  return {
    user,
    isAuthenticated,
    isLoading,
    login,
    register,
    logout,
  };
}
