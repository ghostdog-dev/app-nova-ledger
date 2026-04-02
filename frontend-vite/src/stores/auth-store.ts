import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import type { User } from '@/types';
import { clearStoredTokens, storeAccessToken, getStoredAccessToken, initializeAuth, apiClient, resetRefreshState } from '@/lib/api-client';

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  /** True while verifying stored credentials on app hydration */
  isHydrating: boolean;

  // Actions
  setAuth: (user: User, accessToken: string) => void;
  updateUser: (user: Partial<User>) => void;
  clearAuth: () => void;
  setLoading: (loading: boolean) => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      isHydrating: true,

      setAuth: (user, accessToken) => {
        storeAccessToken(accessToken);
        resetRefreshState(); // Reset circuit breaker on fresh login
        // Refresh token is stored as httpOnly cookie by the backend
        set({ user, isAuthenticated: true, isLoading: false, isHydrating: false });
      },

      updateUser: (partial) =>
        set((state) => ({
          user: state.user ? { ...state.user, ...partial } : null,
        })),

      clearAuth: () => {
        clearStoredTokens();
        set({ user: null, isAuthenticated: false, isLoading: false, isHydrating: false });
      },

      setLoading: (isLoading) => set({ isLoading }),
    }),
    {
      name: 'nova-ledger-auth',
      storage: createJSONStorage(() =>
        typeof window !== 'undefined' ? localStorage : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
      // [M-05] Only persist auth flag — no PII in localStorage
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
      }),
      /**
       * F50 + F05 + M-05 — On rehydrate, ensure state consistency.
       * User PII is no longer persisted in localStorage. After a page
       * refresh we obtain a new access token via the httpOnly refresh
       * cookie and re-fetch the user profile from the API.
       */
      onRehydrateStorage: () => {
        return (state, error) => {
          if (error || !state) {
            return;
          }

          if (!state.isAuthenticated) {
            state.isHydrating = false;
            return;
          }

          // [F05] Token is in-memory only — after page refresh it's always null.
          // Obtain a new access token, then re-fetch the user profile.
          const handleSessionExpired = () => {
            // Clear the httpOnly cookie via backend so the middleware
            // stops redirecting to /dashboard, then redirect to login.
            fetch('/api/v1/accounts/clear-session/', {
              method: 'POST',
              credentials: 'include',
            }).catch(() => {}).finally(() => {
              state.clearAuth();
              if (typeof window !== 'undefined') {
                window.location.href = '/login';
              }
            });
          };

          initializeAuth()
            .then(async (success) => {
              if (!success) {
                handleSessionExpired();
                return;
              }
              try {
                const user = await apiClient.get<User>('/accounts/me/');
                useAuthStore.setState({ user, isHydrating: false });
              } catch {
                handleSessionExpired();
              }
            })
            .catch(() => {
              handleSessionExpired();
            });
        };
      },
    }
  )
);
