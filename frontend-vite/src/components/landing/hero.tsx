import { ArrowDown } from 'lucide-react';
import styles from './hero.module.css';
import { Link } from 'react-router-dom';

export function Hero() {
  return (
    <section className={styles.hero}>
      <div className={styles.bgGrid}>
        {Array.from({ length: 100 }).map((_, i) => (
          <div key={i} className={styles.gridCell} />
        ))}
      </div>

      <div className={styles.container}>
        <div className={styles.leftCol}>
          <div className={styles.badge}>
            <span className={styles.badgeText}>AI-Powered Reconciliation</span>
          </div>

          <h1 className={styles.heroTitle}>
            Financial <br />
            <span className={styles.heroTitleAccent}>clarity</span> <br />
            restored.
          </h1>
        </div>

        <div className={styles.rightCol}>
          <p className={styles.subhead}>
            Nova Ledger connects your fragmented financial ecosystem.
            Invoices, payments, and emails — correlated automatically into
            a single source of truth.
          </p>

          <div className={styles.ctaWrap}>
            <Link to="/register" className={styles.ctaPrimary}>
              Start Free Trial
            </Link>
            <a href="#methodology" className={styles.ctaSecondary}>
              How It Works
            </a>
          </div>
        </div>
      </div>

      <div className={styles.ticker}>
        <div className={styles.tickerInner}>
          <span className={styles.tickerDesktop}>Pennylane • Stripe • Sellsy</span>
          <span className={styles.tickerScroll}>
            Scroll for Analysis <ArrowDown size={14} className={styles.bounceIcon} />
          </span>
          <span className={styles.tickerDesktop}>Secure Protocol: TLS 1.3</span>
        </div>
      </div>
    </section>
  );
}
