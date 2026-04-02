import { ArrowUpRight, Check, Search, Download } from 'lucide-react';
import { cn } from '@/lib/utils';
import styles from './preview.module.css';

const mockData = [
  { date: '2026-02-23', desc: 'AWS S3 Storage', amount: '$42.10', status: 'Matched', source: 'Stripe' },
  { date: '2026-02-22', desc: 'Figma Subscription', amount: '$15.00', status: 'Matched', source: 'Amex' },
  { date: '2026-02-21', desc: 'Consulting: Accha', amount: '$4,500.00', status: 'Pending', source: 'Wise' },
  { date: '2026-02-20', desc: 'WeWork Office', amount: '$850.00', status: 'Matched', source: 'Bank' },
  { date: '2026-02-19', desc: 'Slack Pro', amount: '$12.50', status: 'Matched', source: 'Mastercard' },
];

export function Preview() {
  return (
    <section id="preview" className={styles.section}>
      <div className={styles.container}>
        <div className={styles.headerRow}>
          <div>
            <span className={styles.badge}>Interface Preview</span>
            <h2 className={styles.heading}>
              Your financial <span className={styles.headingAccent}>command center</span>.
            </h2>
          </div>
          <div className={styles.actions}>
            <button className={styles.exportBtn}>
              <Download size={16} /> <span className={styles.exportLabel}>Export CSV</span>
            </button>
          </div>
        </div>

        <div className={styles.dashboard}>
          <div className={styles.toolbar}>
            <div className={styles.toolbarLeft}>
              <div className={styles.dots}>
                <div className={styles.dot} />
                <div className={styles.dot} />
                <div className={styles.dot} />
              </div>
              <div className={styles.divider} />
              <div className={styles.searchBox}>
                <Search size={12} /> Search transactions...
              </div>
            </div>
            <div className={styles.toolbarRight}>Live Connection &bull; 14ms Latency</div>
          </div>

          <div className={styles.tableHeader}>
            <div className={styles.colSpan1}>Date</div>
            <div className={styles.colSpan2}>Description</div>
            <div className={cn(styles.colSpan1, styles.textRight)}>Amount</div>
            <div className={cn(styles.colSpan1, styles.textCenter)}>Source</div>
            <div className={cn(styles.colSpan1, styles.textRight)}>Status</div>
          </div>

          <div>
            {mockData.map((row, i) => (
              <div
                key={i}
                className={styles.tableRow}
              >
                <div className={styles.dateCell}>{row.date}</div>
                <div className={styles.descCell}>
                  {row.desc}
                  <ArrowUpRight size={14} className={styles.arrowIcon} />
                </div>
                <div className={styles.amountCell}>{row.amount}</div>
                <div className={styles.sourceCell}>
                  <span className={styles.sourceTag}>{row.source}</span>
                </div>
                <div className={styles.statusCell}>
                  <span className={cn(styles.statusBadge, row.status === 'Matched' ? styles.badgeMatched : styles.badgePending)}>
                    {row.status === 'Matched' ? <Check size={10} /> : null} {row.status}
                  </span>
                </div>
              </div>
            ))}
            {[1, 2, 3].map((_, i) => (
              <div key={`empty-${i}`} className={styles.emptyRow}>
                <div className={cn(styles.emptyCol1, styles.emptyBar, styles.emptyW16)} />
                <div className={cn(styles.emptyCol2, styles.emptyBar, styles.emptyW32)} />
                <div className={cn(styles.emptyCol1, styles.emptyBar, styles.emptyW12)} />
                <div className={cn(styles.emptyCol1, styles.emptyBar, styles.emptyW16Center)} />
                <div className={cn(styles.emptyCol1, styles.emptyBar, styles.emptyW16Right)} />
              </div>
            ))}
          </div>

          <div className={styles.tableFooter}>
            <span>Showing 1-10 of 1,248 transactions</span>
            <span>Page 1 of 125</span>
          </div>
        </div>
      </div>
    </section>
  );
}
