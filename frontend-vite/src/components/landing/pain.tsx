import { FileWarning } from 'lucide-react';
import styles from './pain.module.css';

const chaosItems = [
  { id: 'INV-001', text: 'Invoice #1024 missing attachment', type: 'error' },
  { id: 'PAY-002', text: 'Stripe payout €420.50 unallocated', type: 'warning' },
  { id: 'EML-003', text: 'Re: Late payment from Client X', type: 'pending' },
  { id: 'XLS-004', text: 'Q3_Final_Final_v2.xlsx corrupted', type: 'error' },
  { id: 'BNK-005', text: 'Bank feed disconnected (3 days ago)', type: 'critical' },
  { id: 'TVA-006', text: 'VAT discrepancy detected in Row 42', type: 'warning' },
];

export function Pain() {
  return (
    <section id="methodology" className={styles.section}>
      <div className={styles.container}>
        <div className={styles.chaosWrap}>
          <div className={styles.chaosBlob} />
          <div className={styles.chaosCard}>
            <div className={styles.chaosHeader}>
              <span className={styles.chaosHeaderLabel}>System Status: Critical</span>
              <FileWarning size={20} className={styles.chaosHeaderIcon} />
            </div>
            <div className={styles.chaosItems}>
              {chaosItems.map((item, i) => (
                <div
                  key={item.id}
                  className={styles.chaosItem}
                >
                  <span className={styles.chaosItemId}>{item.id}</span>
                  <span className={styles.chaosItemText}>{item.text}</span>
                </div>
              ))}
            </div>
            <div className={styles.chaosFooter}>
              <span className={styles.chaosQuote}>&ldquo;Where did the money go?&rdquo;</span>
            </div>
          </div>
        </div>

        <div className={styles.narrative}>
          <h2 className={styles.narrativeTitle}>
            The <span className={styles.narrativeTitleAccent}>entropy</span> of <br /> disconnected tools.
          </h2>
          <p className={styles.narrativeText}>
            Your financial reality is fragmented across Stripe, Pennylane, Gmail, and Excel.
            Data bleeds between the cracks. Hours are lost to manual reconciliation.
            Truth becomes a matter of opinion.
          </p>
          <div className={styles.statsGrid}>
            <div>
              <h3 className={styles.statValue}>12h+</h3>
              <p className={styles.statLabel}>Wasted Weekly</p>
            </div>
            <div>
              <h3 className={styles.statValue}>Error</h3>
              <p className={styles.statLabel}>Prone Process</p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
