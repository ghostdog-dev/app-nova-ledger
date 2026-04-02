import { useState } from 'react';
import { ArrowUpRight, Check, Download, ArrowRight, ChevronDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import styles from './command-center-widget.module.css';
import { Link } from 'react-router-dom';

export interface Transaction {
  date: string;
  desc: string;
  amount: string;
  status: 'matched' | 'pending' | 'orphan';
  source: string;
}

interface CommandCenterWidgetProps {
  transactions: Transaction[];
  totalCount: number;
}

const STATUS_LABELS: Record<string, string> = {
  matched: 'Reconcilie',
  pending: 'En attente',
  orphan: 'Orphelin',
};

export function CommandCenterWidget({
  transactions,
  totalCount,
}: CommandCenterWidgetProps) {
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleRow = (index: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  return (
    <div className={styles.widget}>
      <div className={styles.header}>
        <div className={styles.headerLeft}>
          <span className={styles.badge}>Live</span>
          <span className={styles.title}>Transactions recentes</span>
        </div>
        <div className={styles.headerRight}>
          <span className={styles.liveIndicator}>
            <span className={styles.liveDot} />
            Connecte
          </span>
          <button className={styles.exportBtn}>
            <Download size={12} /> Export
          </button>
        </div>
      </div>

      {/* Table header */}
      <div className={styles.tableHeader}>
        <div className={styles.colPrimary}>Description</div>
        <div className={cn(styles.colPrimary, styles.textRight)}>Montant</div>
        <div className={styles.colSecondary}>Date</div>
        <div className={cn(styles.colSecondary, styles.textCenter)}>Source</div>
        <div className={cn(styles.colSecondary, styles.textRight)}>Statut</div>
        {/* Chevron spacer on mobile */}
        <div className={styles.colChevron} />
      </div>

      {/* Table body */}
      <div>
        {transactions.length === 0 ? (
          <div className={styles.tableRow}>
            <div style={{ gridColumn: '1 / -1', textAlign: 'center', opacity: 0.5 }}>
              Aucune transaction
            </div>
          </div>
        ) : (
          transactions.map((row, i) => {
            const isExpanded = expandedRows.has(i);
            return (
              <div key={i} className={styles.rowWrapper}>
                <div
                  className={styles.tableRow}
                  onClick={() => toggleRow(i)}
                >
                  {/* Primary columns: always visible */}
                  <div className={cn(styles.colPrimary, styles.descCell)}>
                    {row.desc}
                    <ArrowUpRight size={14} className={styles.arrowIcon} />
                  </div>
                  <div className={cn(styles.colPrimary, styles.amountCell)}>{row.amount}</div>

                  {/* Secondary columns: hidden on mobile, visible on tablet+ */}
                  <div className={cn(styles.colSecondary, styles.dateCell)}>{row.date}</div>
                  <div className={cn(styles.colSecondary, styles.sourceCell)}>
                    <span className={styles.sourceTag}>{row.source}</span>
                  </div>
                  <div className={cn(styles.colSecondary, styles.statusCell)}>
                    <span
                      className={cn(
                        styles.statusBadge,
                        row.status === 'matched' && styles.badgeMatched,
                        row.status === 'pending' && styles.badgePending,
                        row.status === 'orphan' && styles.badgeOrphan,
                      )}
                    >
                      {row.status === 'matched' ? <Check size={10} /> : null}
                      {STATUS_LABELS[row.status]}
                    </span>
                  </div>

                  {/* Mobile chevron toggle */}
                  <div className={styles.colChevron}>
                    <ChevronDown
                      size={14}
                      className={cn(styles.chevronIcon, isExpanded && styles.chevronExpanded)}
                    />
                  </div>
                </div>

                {/* Expanded detail area (mobile only) */}
                <div className={cn(styles.expandedDetail, isExpanded && styles.expandedDetailOpen)}>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Date</span>
                    <span className={styles.detailValue}>{row.date}</span>
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Source</span>
                    <span className={styles.detailValue}>
                      <span className={styles.sourceTag}>{row.source}</span>
                    </span>
                  </div>
                  <div className={styles.detailRow}>
                    <span className={styles.detailLabel}>Statut</span>
                    <span className={styles.detailValue}>
                      <span
                        className={cn(
                          styles.statusBadge,
                          row.status === 'matched' && styles.badgeMatched,
                          row.status === 'pending' && styles.badgePending,
                          row.status === 'orphan' && styles.badgeOrphan,
                        )}
                      >
                        {row.status === 'matched' ? <Check size={10} /> : null}
                        {STATUS_LABELS[row.status]}
                      </span>
                    </span>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>

      <div className={styles.tableFooter}>
        <span>{totalCount.toLocaleString('fr-FR')} transactions au total</span>
        <Link to="/transactions" className={styles.viewAllLink}>
          Voir tout <ArrowRight size={12} />
        </Link>
      </div>
    </div>
  );
}
