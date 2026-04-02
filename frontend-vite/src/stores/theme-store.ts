import { create } from 'zustand';

type Theme = 'light' | 'dark';

interface ThemeState {
  theme: Theme;
  toggle: () => void;
  setTheme: (theme: Theme) => void;
}

function getInitialTheme(): Theme {
  const stored = localStorage.getItem('nova-ledger-theme');
  if (stored === 'dark' || stored === 'light') return stored;
  if (window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
  return 'light';
}

function applyTheme(theme: Theme) {
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('nova-ledger-theme', theme);
}

export const useThemeStore = create<ThemeState>((set) => {
  const initial = getInitialTheme();
  // Ensure DOM is in sync (covers the case where the blocking script
  // already set the attribute — this is a no-op in that case).
  applyTheme(initial);

  return {
    theme: initial,

    toggle: () =>
      set((state) => {
        const next = state.theme === 'light' ? 'dark' : 'light';
        applyTheme(next);
        return { theme: next };
      }),

    setTheme: (theme) => {
      applyTheme(theme);
      set({ theme });
    },
  };
});
