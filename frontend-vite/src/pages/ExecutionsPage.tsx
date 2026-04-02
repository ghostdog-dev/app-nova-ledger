import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Plus,
  PlaySquare,
  ArrowUpRight,
  Check,
  ChevronDown,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { Button } from '@/components/ui/button';
import { Alert } from '@/components/ui/alert';
import { useExecutions } from '@/hooks/use-executions';
import { formatDate } from '@/lib/utils';
import type { Execution } from '@/types';
import styles from './ExecutionsPage.module.css';
import { Link, useNavigate } from 'react-router-dom';


// ── Status helpers ───────────────────────────────────────────────────────────

const STATUS_LABELS: Record<string, string> = {
  completed: 'Termine',
  pending: 'En attente',
  running: 'En cours',
  collecting: 'Collecte',
  normalizing: 'Normalisation',
  correlating: 'Correlation',
  detecting: 'Detection',
  generating: 'Generation',
  error: 'Erreur',
  failed: 'Echoue',
  cancelled: 'Annule',
};

function statusBadgeClass(s: string): string {
  if (s === 'completed') return styles.badgeCompleted;
  if (s === 'error' || s === 'failed' || s === 'cancelled') return styles.badgeFailed;
  return styles.badgePending;
}

// ── Row ──────────────────────────────────────────────────────────────────────

function ExecutionRow({
  execution,
  isExpanded,
  onToggle,
}: {
  execution: Execution;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const summary = execution.summary;

  return (
    <div className={styles.rowGroup}>
      {/* Main row — wraps in a Link for navigation on desktop */}
      <div className={styles.tableRow} onClick={onToggle}>
        {/* Expand button (mobile only, hidden on desktop via CSS) */}
        <div
          className={styles.expandBtn}
          role="button"
          tabIndex={0}
          aria-expanded={isExpanded}
          aria-label="Expand row details"
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              onToggle();
            }
          }}
        >
          <ChevronDown
            className={cn(
              styles.expandChevron,
              isExpanded && styles.expandChevronOpen
            )}
          />
        </div>

        {/* Primary columns (always visible): date range, duration, status */}
        <div className={styles.primaryCols}>
          <Link
            to={`/executions/${execution.publicId}`}
            className={styles.dateRangeCell}
            onClick={(e) => e.stopPropagation()}
          >
            {formatDate(execution.dateFrom)} → {formatDate(execution.dateTo)}
            <ArrowUpRight size={14} className={styles.arrowIcon} />
          </Link>
          <div className={styles.durationCell}>
            {execution.durationSeconds != null
              ? `${Math.round(execution.durationSeconds)}s`
              : '—'}
          </div>
        </div>

        {/* Secondary columns (desktop only) */}
        <div className={styles.secondaryCols}>
          <div className={styles.summaryCell}>
            {summary ? (
              <>
                <span className={styles.summaryItem}>
                  {summary.invoicesProcessed} fact.
                </span>
                <span className={styles.summaryHighlight}>
                  {summary.reconciliationRate}%
                </span>
                <span className={styles.summaryItem}>
                  {summary.anomaliesDetected} anom.
                </span>
              </>
            ) : (
              <span className={styles.summaryItem}>—</span>
            )}
          </div>
        </div>

        {/* Status (always visible) */}
        <div className={styles.statusCell}>
          <span className={cn(styles.statusBadge, statusBadgeClass(execution.status))}>
            {execution.status === 'completed' ? <Check size={10} /> : null}
            {STATUS_LABELS[execution.status] ?? execution.status}
          </span>
        </div>
      </div>

      {/* Expanded detail (mobile only, hidden on desktop via CSS) */}
      <div
        className={cn(
          styles.expandedDetail,
          isExpanded && styles.expandedDetailOpen
        )}
      >
        <div className={styles.expandedDetailInner}>
          {summary ? (
            <>
              <div className={styles.detailRow}>
                <span>Factures</span>
                <span>{summary.invoicesProcessed}</span>
              </div>
              <div className={styles.detailRow}>
                <span>Taux reconciliation</span>
                <span>{summary.reconciliationRate}%</span>
              </div>
              <div className={styles.detailRow}>
                <span>Anomalies</span>
                <span>{summary.anomaliesDetected}</span>
              </div>
            </>
          ) : (
            <div className={styles.detailRow}>
              <span>Resultats</span>
              <span>—</span>
            </div>
          )}
          <div className={styles.detailRow}>
            <span>Duree</span>
            <span>
              {execution.durationSeconds != null
                ? `${Math.round(execution.durationSeconds)}s`
                : '—'}
            </span>
          </div>
          <div style={{ marginTop: '0.5rem' }}>
            <Link
              to={`/executions/${execution.publicId}`}
              style={{
                fontFamily: 'var(--font-mono)',
                fontSize: '0.75rem',
                color: 'var(--color-teal)',
                textDecoration: 'underline',
                textTransform: 'uppercase',
                letterSpacing: '0.05em',
              }}
            >
              Voir details →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function ExecutionsPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { executions, isLoading, error, refetch } = useExecutions();
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = (id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.title}>{t('executions.title')}</h1>
          <p className={styles.subtitle}>{t('executions.subtitle')}</p>
        </div>
        <Button
          size="sm"
          leftIcon={<Plus className={styles.iconSm} />}
          onClick={() => navigate('/executions/new')}
        >
          {t('executions.newExecution')}
        </Button>
      </div>

      {error && (
        <Alert variant="error" onClose={refetch}>
          {error}
        </Alert>
      )}

      {/* Dark table */}
      <div className={styles.tableContainer}>
        {/* Toolbar */}
        <div className={styles.tableToolbar}>
          <div className={styles.toolbarLeft}>
            <span className={styles.badge}>Analyses</span>
            <span className={styles.tableTitle}>Historique des executions</span>
          </div>
        </div>

        {/* Table header (desktop only, shown via CSS) */}
        <div className={styles.tableHeader}>
          <div>Periode</div>
          <div>Resultats</div>
          <div className={styles.textRight}>Duree</div>
          <div className={styles.textRight}>Statut</div>
        </div>

        {/* Table body */}
        {isLoading ? (
          <div className={styles.loading}>
            <Loader2 className={styles.spinner} />
            Chargement...
          </div>
        ) : executions.length === 0 ? (
          <div className={styles.emptyState}>
            <PlaySquare className={styles.emptyIcon} />
            <p className={styles.emptyTitle}>{t('executions.noExecutions')}</p>
            <p className={styles.emptyDesc}>{t('executions.noExecutionsDescription')}</p>
            <Button
              leftIcon={<Plus className={styles.iconSm} />}
              onClick={() => navigate('/executions/new')}
            >
              {t('executions.newExecution')}
            </Button>
          </div>
        ) : (
          executions.map((execution) => (
            <ExecutionRow
              key={execution.publicId}
              execution={execution}
              isExpanded={expandedRows.has(execution.publicId)}
              onToggle={() => toggleRow(execution.publicId)}
            />
          ))
        )}

        {/* Footer */}
        {executions.length > 0 && (
          <div className={styles.tableFooter}>
            <span>
              {executions.length} analyse{executions.length > 1 ? 's' : ''} au total
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
