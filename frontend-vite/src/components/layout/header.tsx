import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Menu, Globe, User, Settings, LogOut, ChevronDown, Sun, Moon } from 'lucide-react';
import { clsx } from 'clsx';
import { useAuthStore } from '@/stores/auth-store';
import { apiClient } from '@/lib/api-client';
import { getInitials } from '@/lib/utils';
import { localeLabels, type Locale, locales } from '@/i18n/config';
import { setLocale } from '@/i18n';
import { useThemeStore } from '@/stores/theme-store';
import { NotificationBell } from '@/components/notifications/notification-bell';
import { CompanySwitcher } from '@/components/layout/company-switcher';
import styles from './header.module.css';
import { useNavigate } from 'react-router-dom';

interface HeaderProps {
  onMenuToggle?: () => void;
}

export function Header({ onMenuToggle }: HeaderProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, clearAuth } = useAuthStore();
  const { theme, toggle: toggleTheme } = useThemeStore();

  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [langMenuOpen, setLangMenuOpen] = useState(false);
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLocaleChange = (locale: Locale) => {
    setLangMenuOpen(false);
    setLocale(locale);
  };

  /**
   * F95 — Proper logout flow: call backend to blacklist the refresh token,
   * then clear client-side state and redirect to login.
   */
  const handleLogout = async () => {
    setUserMenuOpen(false);
    setIsLoggingOut(true);
    try {
      // Call backend logout endpoint to blacklist the refresh token
      // The refresh token is sent automatically as httpOnly cookie
      await apiClient.post('/accounts/logout/');
    } catch {
      // Even if the backend call fails, we still clear client state
      // to ensure the user is logged out locally
    } finally {
      clearAuth();
      setIsLoggingOut(false);
      navigate('/login');
    }
  };

  return (
    <header className={styles.header}>
      {/* Mobile menu toggle */}
      <button
        type="button"
        onClick={onMenuToggle}
        className={styles.mobileToggle}
        aria-label="Toggle menu"
      >
        <Menu className={styles.toggleIcon} aria-hidden="true" />
      </button>

      {/* Spacer */}
      <div className={styles.spacer} />

      {/* Right actions */}
      <div className={styles.actions}>
        {/* Company switcher */}
        <CompanySwitcher />

        {/* Notification bell */}
        <NotificationBell />

        {/* Theme toggle */}
        <button
          type="button"
          onClick={toggleTheme}
          className={styles.dropdownBtn}
          aria-label={theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'}
        >
          {theme === 'dark' ? (
            <Sun className={styles.langIcon} aria-hidden="true" />
          ) : (
            <Moon className={styles.langIcon} aria-hidden="true" />
          )}
        </button>

        {/* Language switcher */}
        <div className={styles.relative}>
          <button
            type="button"
            onClick={() => {
              setLangMenuOpen(!langMenuOpen);
              setUserMenuOpen(false);
            }}
            className={styles.dropdownBtn}
            aria-label={t('header.language')}
            aria-expanded={langMenuOpen}
            aria-haspopup="menu"
          >
            <Globe className={styles.langIcon} aria-hidden="true" />
            <ChevronDown className={styles.langChevron} aria-hidden="true" />
          </button>

          {langMenuOpen && (
            <>
              <div
                className={styles.overlay}
                onClick={() => setLangMenuOpen(false)}
                aria-hidden="true"
              />
              <div
                className={styles.dropdown}
                role="menu"
                aria-label={t('header.language')}
              >
                {locales.map((locale) => (
                  <button
                    key={locale}
                    type="button"
                    role="menuitem"
                    onClick={() => handleLocaleChange(locale)}
                    className={styles.dropdownItem}
                  >
                    {localeLabels[locale]}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* User menu */}
        <div className={styles.relative}>
          <button
            type="button"
            onClick={() => {
              setUserMenuOpen(!userMenuOpen);
              setLangMenuOpen(false);
            }}
            className={styles.userBtn}
            aria-expanded={userMenuOpen}
            aria-haspopup="menu"
            aria-label={t('header.myAccount')}
          >
            <span className={styles.avatar}>
              {user ? getInitials(user.firstName, user.lastName) : '?'}
            </span>
            {user && (
              <span className={styles.userName}>
                {user.firstName} {user.lastName}
              </span>
            )}
            <ChevronDown className={styles.chevron} aria-hidden="true" />
          </button>

          {userMenuOpen && (
            <>
              <div
                className={styles.overlay}
                onClick={() => setUserMenuOpen(false)}
                aria-hidden="true"
              />
              <div
                className={clsx(styles.dropdown, styles.userDropdown)}
                role="menu"
              >
                {user && (
                  <>
                    <div className={styles.userMenuHeader}>
                      <p className={styles.userMenuName}>
                        {user.firstName} {user.lastName}
                      </p>
                      <p className={styles.userMenuEmail}>{user.email}</p>
                    </div>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => { setUserMenuOpen(false); navigate('/settings'); }}
                      className={styles.dropdownItem}
                    >
                      <User className={clsx(styles.langIcon, styles.iconMuted)} aria-hidden="true" />
                      {t('header.profile')}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={() => { setUserMenuOpen(false); navigate('/settings'); }}
                      className={styles.dropdownItem}
                    >
                      <Settings className={clsx(styles.langIcon, styles.iconMuted)} aria-hidden="true" />
                      {t('header.settings')}
                    </button>
                    <div className={styles.divider} />
                  </>
                )}
                <button
                  type="button"
                  role="menuitem"
                  onClick={handleLogout}
                  disabled={isLoggingOut}
                  className={clsx(styles.dropdownItem, styles.logoutItem)}
                >
                  <LogOut className={styles.langIcon} aria-hidden="true" />
                  {isLoggingOut ? t('header.loggingOut') : t('header.logout')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
}
