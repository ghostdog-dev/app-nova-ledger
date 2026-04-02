import { Mail, Landmark, CreditCard, Receipt, Database, Boxes, Workflow } from 'lucide-react';
import styles from './how-it-works.module.css';

export function HowItWorks() {
  return (
    <section id="features" className={styles.section}>
      <div className={styles.bgLines}>
        <div className={styles.verticalLine} />
        <div className={styles.horizontalLine} />
      </div>

      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.badge}>
            <span className={styles.badgeText}>Correlation Engine</span>
          </div>
          <h2 className={styles.title}>
            Order from <span className={styles.titleAccent}>chaos</span>.
          </h2>
          <p className={styles.subtitle}>
            Nova Ledger ingests raw data streams, identifies relationships, and synthesizes
            a unified ledger. No manual entry. No guesswork.
          </p>
        </div>

        <div className={styles.grid}>
          <div className={styles.inputCol}>
            {[
              { icon: Mail, label: 'Business Email', sub: 'Gmail / Outlook' },
              { icon: CreditCard, label: 'Payment Gateways', sub: 'Stripe / GoCardless' },
              { icon: Landmark, label: 'Banking Feeds', sub: 'Qonto / Wise' },
            ].map((item, idx) => (
              <div
                key={idx}
                className={styles.inputCard}
              >
                <item.icon size={24} className={styles.inputCardIcon} />
                <div>
                  <h4 className={styles.inputCardLabel}>{item.label}</h4>
                  <p className={styles.inputCardSub}>{item.sub}</p>
                </div>
                <div className={styles.connectionStubRight} />
              </div>
            ))}
          </div>

          <div className={styles.centerCol}>
            <div className={styles.core}>
              <div className={styles.coreInner}>
                <Workflow size={48} className={styles.coreIcon} />
                <h3 className={styles.coreTitle}>IA Core</h3>
                <p className={styles.coreSub}>AI Correlation Active</p>
              </div>
              <div className={styles.orbitalRing1} />
              <div className={styles.orbitalRing2} />
            </div>
          </div>

          <div className={styles.outputCol}>
            {[
              { icon: Receipt, label: 'Unified Invoices', sub: 'Auto-matched' },
              { icon: Database, label: 'Clean Ledger', sub: 'Accounting Ready' },
              { icon: Boxes, label: 'Visual Reports', sub: 'Board Presentation' },
            ].map((item, idx) => (
              <div
                key={idx}
                className={styles.outputCard}
              >
                <div className={styles.connectionStubLeft} />
                <item.icon size={24} className={styles.outputCardIcon} />
                <div>
                  <h4 className={styles.outputCardLabel}>{item.label}</h4>
                  <p className={styles.outputCardSub}>{item.sub}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
