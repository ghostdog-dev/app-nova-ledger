import { Outlet } from 'react-router-dom';
import styles from './AuthLayout.module.css';

/**
 * Auth layout — centered card on editorial background, no sidebar.
 */
export function AuthLayout() {
  return (
    <div className={styles.container}>
      {/* App brand */}
      <div className={styles.brand}>
        <span className={styles.brandTitle}>
          <span className={styles.brandAccent}>Nova</span> Ledger
        </span>
        <p className={styles.brandSub}>Réconciliation intelligente</p>
      </div>

      {/* Auth card */}
      <div className={styles.card}>
        <Outlet />
      </div>

      {/* Footer */}
      <p className={styles.copyright}>
        &copy; {new Date().getFullYear()} Nova Ledger. All rights reserved.
      </p>
    </div>
  );
}
