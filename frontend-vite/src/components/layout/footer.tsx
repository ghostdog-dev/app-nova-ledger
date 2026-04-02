import { useTranslation } from 'react-i18next';
import styles from './footer.module.css';

export function Footer() {
  const { t } = useTranslation();
  const year = new Date().getFullYear();

  return (
    <footer className={styles.footer}>
      <div className={styles.inner}>
        <p>
          &copy; {year} {t('common.appName')}. All rights reserved.
        </p>
        <nav aria-label="Footer links" className={styles.links}>
          <a href="#" className={styles.link}>
            Privacy
          </a>
          <a href="#" className={styles.link}>
            Terms
          </a>
          <a href="#" className={styles.link}>
            Support
          </a>
        </nav>
      </div>
    </footer>
  );
}
