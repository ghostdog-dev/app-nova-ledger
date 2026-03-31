import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Link2,
  Database,
  PlaySquare,
  ArrowLeftRight,
  Settings,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { clsx } from 'clsx';
import { useState } from 'react';
import styles from './sidebar.module.css';
import { Link, useLocation } from 'react-router-dom';

interface NavItem {
  labelKey: string;
  href: string;
  icon: React.ComponentType<{ className?: string }>;
}

const navItems: NavItem[] = [
  { labelKey: 'nav.dashboard', href: '/dashboard', icon: LayoutDashboard },
  { labelKey: 'nav.connections', href: '/connections', icon: Link2 },
  { labelKey: 'nav.sources', href: '/sources', icon: Database },
  { labelKey: 'nav.executions', href: '/executions', icon: PlaySquare },
  { labelKey: 'nav.transactions', href: '/transactions', icon: ArrowLeftRight },
  { labelKey: 'nav.settings', href: '/settings', icon: Settings },
];

interface SidebarProps {
  defaultCollapsed?: boolean;
  onNavigate?: () => void;
}

export function Sidebar({ defaultCollapsed = false, onNavigate }: SidebarProps) {
  const { t } = useTranslation();
  const { pathname } = useLocation();
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <aside
      className={clsx(
        styles.sidebar,
        collapsed ? styles.collapsed : styles.expanded
      )}
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className={clsx(styles.logoArea, collapsed ? styles.logoAreaCollapsed : styles.logoAreaExpanded)}>
        {collapsed ? (
          <span className={clsx(styles.logoText, styles.logoAccent)} title={t('common.appName')}>
            NL
          </span>
        ) : (
          <span className={styles.logoText}>
            <span className={styles.logoAccent}>Nova</span> Ledger
          </span>
        )}
      </div>

      {/* Navigation */}
      <nav className={styles.nav}>
        <ul className={styles.navList} role="list">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);

            return (
              <li key={item.href} className={styles.navItem}>
                <Link to={item.href}
                  className={clsx(
                    styles.navLink,
                    isActive && styles.navLinkActive,
                    collapsed && styles.navLinkCollapsed
                  )}
                  aria-current={isActive ? 'page' : undefined}
                  title={collapsed ? t(item.labelKey as Parameters<typeof t>[0]) : undefined}
                  onClick={onNavigate}
                >
                  <Icon className={styles.navIcon} aria-hidden="true" />
                  {!collapsed && <span>{t(item.labelKey as Parameters<typeof t>[0])}</span>}
                </Link>
              </li>
            );
          })}
        </ul>
      </nav>

      {/* Collapse toggle */}
      <div className={styles.collapseArea}>
        <button
          type="button"
          onClick={() => setCollapsed(!collapsed)}
          className={clsx(
            styles.collapseBtn,
            collapsed && styles.collapseBtnCollapsed
          )}
          aria-label={collapsed ? t('sidebar.expand') : t('sidebar.collapse')}
        >
          {collapsed ? (
            <ChevronRight className={styles.navIcon} aria-hidden="true" />
          ) : (
            <>
              <ChevronLeft className={styles.navIcon} aria-hidden="true" />
              <span>{t('sidebar.collapse')}</span>
            </>
          )}
        </button>
      </div>
    </aside>
  );
}
