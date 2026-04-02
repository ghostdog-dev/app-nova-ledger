import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { apiClient, getStoredAccessToken, initializeAuth } from '@/lib/api-client';
import type { Company, CompanyPlan, CompanyUsage, CompanyMember, PaginatedResponse } from '@/types';

interface CompanyState {
  companies: Company[];
  activeCompany: Company | null;
  /** F51 — Only the company publicId (UUID) is persisted to storage */
  _persistedCompanyId: string | null;
  plan: CompanyPlan | null;
  usage: CompanyUsage | null;
  members: CompanyMember[];
  isLoading: boolean;

  // Actions
  fetchCompanies: () => Promise<void>;
  switchCompany: (company: Company) => void;
  fetchPlan: () => Promise<void>;
  fetchUsage: () => Promise<void>;
  fetchMembers: () => Promise<void>;
  setActiveCompany: (company: Company) => void;
}

export const useCompanyStore = create<CompanyState>()(
  persist(
    (set, get) => ({
      companies: [],
      activeCompany: null,
      _persistedCompanyId: null,
      plan: null,
      usage: null,
      members: [],
      isLoading: false,

      fetchCompanies: async () => {
        // Wait for auth to be ready (access token restored from refresh cookie)
        // before calling the API. This prevents 401 races on page load.
        if (!getStoredAccessToken()) {
          const ok = await initializeAuth();
          if (!ok) return; // No valid session — don't attempt API calls
        }
        try {
          const data = await apiClient.get<PaginatedResponse<Company>>('/companies/');
          const companies = data.results;
          set({ companies });

          // If we have a persisted company ID from storage, restore the full object
          const { activeCompany, _persistedCompanyId } = get();
          if (!activeCompany && _persistedCompanyId) {
            const restored = companies.find((c) => c.publicId === _persistedCompanyId);
            if (restored) {
              set({ activeCompany: restored });
              return;
            }
          }

          // If no active company is set but we have companies, set the first one
          if (!activeCompany && companies.length > 0) {
            set({ activeCompany: companies[0], _persistedCompanyId: companies[0].publicId });
          }
        } catch {
          // Silently ignore -- user may have no companies yet
        }
      },

      switchCompany: (company: Company) => {
        set({
          activeCompany: company,
          _persistedCompanyId: company.publicId,
          plan: null,
          usage: null,
          members: [],
          isLoading: false,
        });
        // Trigger a page reload to refresh all company-scoped data
        if (typeof window !== 'undefined') {
          window.location.reload();
        }
      },

      fetchPlan: async () => {
        const id = get().activeCompany?.publicId;
        if (!id) return;
        try {
          const data = await apiClient.get<CompanyPlan>(`/companies/${id}/plan/`);
          set({ plan: data });
        } catch {
          // Ignore
        }
      },

      fetchUsage: async () => {
        const id = get().activeCompany?.publicId;
        if (!id) return;
        try {
          const data = await apiClient.get<CompanyUsage>(`/companies/${id}/usage/`);
          set({ usage: data });
        } catch {
          // Ignore
        }
      },

      fetchMembers: async () => {
        const id = get().activeCompany?.publicId;
        if (!id) return;
        try {
          const data = await apiClient.get<PaginatedResponse<CompanyMember>>(
            `/companies/${id}/members/`
          );
          set({ members: data.results });
        } catch {
          set({ members: [] });
        }
      },

      setActiveCompany: (company) =>
        set({ activeCompany: company, _persistedCompanyId: company.publicId }),
    }),
    {
      name: 'nova-ledger-company',
      storage: createJSONStorage(() =>
        typeof window !== 'undefined'
          ? localStorage
          : { getItem: () => null, setItem: () => {}, removeItem: () => {} }
      ),
      /**
       * F51 — Only persist the company publicId (UUID), not the full company object.
       * The full object (which may contain SIRET, owner email, etc.) is
       * re-fetched from the API on each page load via fetchCompanies().
       */
      partialize: (state) => ({
        _persistedCompanyId: state._persistedCompanyId,
      }),
    }
  )
);
