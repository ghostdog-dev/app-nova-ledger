import { useState, useMemo, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronUp, ChevronDown, ChevronsUpDown, Search, Eye, Edit3, PenLine } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { CorrelationDetailModal } from './correlation-detail-modal';
import { formatAmount, formatDate, formatScore } from '@/lib/utils';
import type { Correlation, CorrelationStatus, CorrelationUpdatePayload, SortDirection } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './correlations-table.module.css';

interface CorrelationsTableProps {
  correlations: Correlation[];
  onEdit: (id: string, patch: CorrelationUpdatePayload) => Promise<void>;
}

type SortField = 'numero' | 'dateEmission' | 'fournisseur' | 'montantTtc' | 'scoreConfiance' | 'statut';

type FilterStatus = 'all' | CorrelationStatus;

const STATUS_VARIANT: Record<CorrelationStatus, BadgeVariant> = {
  reconciled: 'success',
  reconciled_with_alert: 'warning',
  unpaid: 'error',
  orphan_payment: 'error',
  uncertain: 'default',
};

function SortIcon({ field, current, direction }: { field: SortField; current: SortField | null; direction: SortDirection }) {
  if (current !== field) return <ChevronsUpDown className={clsx(styles.sortIcon, styles.sortIconDefault)} aria-hidden="true" />;
  return direction === 'asc'
    ? <ChevronUp className={clsx(styles.sortIcon, styles.sortIconActive)} aria-hidden="true" />
    : <ChevronDown className={clsx(styles.sortIcon, styles.sortIconActive)} aria-hidden="true" />;
}

const FILTER_TABS: FilterStatus[] = ['all', 'reconciled', 'reconciled_with_alert', 'unpaid', 'orphan_payment', 'uncertain'];

export function CorrelationsTable({ correlations, onEdit }: CorrelationsTableProps) {
  const { t } = useTranslation();

  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<FilterStatus>('all');
  const [sortField, setSortField] = useState<SortField | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>('asc');
  const [detailCorrelation, setDetailCorrelation] = useState<Correlation | null>(null);
  const [detailMode, setDetailMode] = useState<'view' | 'edit'>('view');
  const [expandedRows, setExpandedRows] = useState<Set<string>>(new Set());

  const toggleRow = useCallback((id: string) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const handleSort = useCallback((field: SortField) => {
    if (sortField === field) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  }, [sortField]);

  const filtered = useMemo(() => {
    let rows = correlations;

    // Status filter
    if (statusFilter !== 'all') {
      rows = rows.filter((c) => c.statut === statusFilter);
    }

    // Search
    if (search.trim()) {
      const q = search.toLowerCase();
      rows = rows.filter(
        (c) =>
          c.invoice?.numero.toLowerCase().includes(q) ||
          c.invoice?.fournisseur.toLowerCase().includes(q) ||
          c.payment?.reference?.toLowerCase().includes(q)
      );
    }

    // Sort
    if (sortField) {
      rows = [...rows].sort((a, b) => {
        let aVal: string | number;
        let bVal: string | number;

        switch (sortField) {
          case 'numero':
            aVal = a.invoice?.numero ?? '';
            bVal = b.invoice?.numero ?? '';
            break;
          case 'dateEmission':
            aVal = a.invoice?.dateEmission ?? '';
            bVal = b.invoice?.dateEmission ?? '';
            break;
          case 'fournisseur':
            aVal = a.invoice?.fournisseur ?? '';
            bVal = b.invoice?.fournisseur ?? '';
            break;
          case 'montantTtc':
            aVal = a.invoice ? parseFloat(a.invoice.montantTtc) : 0;
            bVal = b.invoice ? parseFloat(b.invoice.montantTtc) : 0;
            break;
          case 'scoreConfiance':
            aVal = a.scoreConfiance;
            bVal = b.scoreConfiance;
            break;
          case 'statut':
            aVal = a.statut;
            bVal = b.statut;
            break;
          default:
            aVal = '';
            bVal = '';
        }

        const cmp =
          typeof aVal === 'number' && typeof bVal === 'number'
            ? aVal - bVal
            : String(aVal ?? '').localeCompare(String(bVal ?? ''));
        return sortDirection === 'asc' ? cmp : -cmp;
      });
    }

    return rows;
  }, [correlations, statusFilter, search, sortField, sortDirection]);

  // Status counts for filter tabs
  const counts = useMemo(() => {
    const c: Partial<Record<FilterStatus, number>> = { all: correlations.length };
    for (const cor of correlations) {
      c[cor.statut] = (c[cor.statut] ?? 0) + 1;
    }
    return c;
  }, [correlations]);

  function ThCell({ field, children }: { field: SortField; children: React.ReactNode }) {
    return (
      <th
        className={styles.th}
        onClick={() => handleSort(field)}
        aria-sort={sortField === field ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'}
      >
        <span className={styles.thInner}>
          {children}
          <SortIcon field={field} current={sortField} direction={sortDirection} />
        </span>
      </th>
    );
  }

  function miniBarFillClass(score: number) {
    if (score >= 90) return styles.miniBarFillGreen;
    if (score >= 70) return styles.miniBarFillAmber;
    return styles.miniBarFillRed;
  }

  return (
    <div className={styles.wrap}>
      {/* Search + Filter bar */}
      <div className={styles.filterBar}>
        <div className={styles.searchWrap}>
          <Input
            type="search"
            placeholder={t('executions.results.search')}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            leftIcon={<Search style={{ width: '1rem', height: '1rem' }} />}
          />
        </div>

        <nav
          className={styles.filterNav}
          aria-label="Filter by status"
        >
          {FILTER_TABS.map((status) => (
            <button
              key={status}
              type="button"
              onClick={() => setStatusFilter(status)}
              className={clsx(
                styles.filterBtn,
                statusFilter === status && styles.filterBtnActive
              )}
            >
              {t(`executions.results.filters.${status}` as Parameters<typeof t>[0])}
              <span className={styles.filterBtnCount}>
                {counts[status] ?? 0}
              </span>
            </button>
          ))}
        </nav>
      </div>

      {/* Table wrapper */}
      <div className={styles.tableWrap}>
        {/* === Mobile card list (visible < 1024px) === */}
        <div className={styles.mobileList}>
          {filtered.length === 0 ? (
            <div className={styles.mobileEmpty}>
              {search || statusFilter !== 'all'
                ? t('executions.results.noResultsFiltered')
                : t('executions.results.noResults')}
            </div>
          ) : (
            filtered.map((correlation) => {
              const isExpanded = expandedRows.has(correlation.publicId);
              return (
                <div key={correlation.publicId} className={styles.mobileRowGroup}>
                  {/* Summary row */}
                  <div
                    className={clsx(styles.mobileRow, correlation.isManual && styles.trManual)}
                    onClick={() => toggleRow(correlation.publicId)}
                  >
                    <div
                      className={styles.mobileExpandBtn}
                      role="button"
                      tabIndex={0}
                      aria-expanded={isExpanded}
                      aria-label="Expand correlation details"
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          toggleRow(correlation.publicId);
                        }
                      }}
                    >
                      <ChevronDown
                        className={clsx(
                          styles.expandChevron,
                          isExpanded && styles.expandChevronOpen
                        )}
                      />
                    </div>

                    <div className={styles.mobilePrimaryCols}>
                      {/* Invoice ref */}
                      <div className={styles.mobileInvoiceRef}>
                        {correlation.invoice?.numero ?? '\u2014'}
                        {correlation.isManual && (
                          <PenLine className={styles.editedMark} aria-label={t('executions.correlation.isEdited')} />
                        )}
                      </div>
                      {/* Payment ref */}
                      <div className={styles.mobilePaymentRef}>
                        {correlation.payment?.reference ?? '\u2014'}
                      </div>
                      {/* Amount */}
                      <div className={styles.mobileAmount}>
                        {correlation.invoice
                          ? formatAmount(parseFloat(correlation.invoice.montantTtc), correlation.invoice.devise)
                          : '\u2014'}
                      </div>
                    </div>

                    {/* Confidence score */}
                    <div className={styles.mobileScore}>
                      <div className={styles.mobileScoreMiniBar}>
                        <div
                          className={miniBarFillClass(correlation.scoreConfiance)}
                          style={{ width: `${correlation.scoreConfiance}%` }}
                        />
                      </div>
                      <span className={styles.mobileScoreText}>
                        {formatScore(correlation.scoreConfiance)}
                      </span>
                    </div>
                  </div>

                  {/* Expanded detail */}
                  <div
                    className={clsx(
                      styles.mobileExpandedDetail,
                      isExpanded && styles.mobileExpandedDetailOpen
                    )}
                  >
                    <div className={styles.mobileExpandedDetailInner}>
                      <div className={styles.mobileDetailRow}>
                        <span>{t('executions.results.table.date')}</span>
                        <span>{correlation.invoice ? formatDate(correlation.invoice.dateEmission) : '\u2014'}</span>
                      </div>
                      <div className={styles.mobileDetailRow}>
                        <span>{t('executions.results.table.vendor')}</span>
                        <span>{correlation.invoice?.fournisseur ?? '\u2014'}</span>
                      </div>
                      <div className={styles.mobileDetailRow}>
                        <span>{t('executions.results.table.paidAmount')}</span>
                        <span>
                          {correlation.payment
                            ? formatAmount(parseFloat(correlation.payment.montant), correlation.payment.devise)
                            : '\u2014'}
                        </span>
                      </div>
                      <div className={styles.mobileDetailRow}>
                        <span>{t('executions.results.table.status')}</span>
                        <span>
                          <Badge variant={STATUS_VARIANT[correlation.statut]} dot>
                            {t(`executions.correlationStatus.${correlation.statut}` as Parameters<typeof t>[0])}
                          </Badge>
                        </span>
                      </div>
                      <div className={styles.mobileDetailRow}>
                        <span>{t('executions.results.table.confidence')}</span>
                        <span>{formatScore(correlation.scoreConfiance)}</span>
                      </div>

                      {/* Actions */}
                      <div className={styles.mobileActions}>
                        <button
                          type="button"
                          className={styles.mobileActionBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDetailCorrelation(correlation);
                            setDetailMode('view');
                          }}
                        >
                          <Eye className={styles.actionIcon} />
                          {t('executions.results.viewDetails')}
                        </button>
                        <button
                          type="button"
                          className={styles.mobileActionBtn}
                          onClick={(e) => {
                            e.stopPropagation();
                            setDetailCorrelation(correlation);
                            setDetailMode('edit');
                          }}
                        >
                          <Edit3 className={styles.actionIcon} />
                          {t('executions.results.editCorrelation')}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* === Desktop table (visible >= 1024px) === */}
        <table className={styles.table} aria-label="Correlations">
          <thead className={styles.thead}>
            <tr>
              <ThCell field="numero">{t('executions.results.table.invoice')}</ThCell>
              <ThCell field="dateEmission">{t('executions.results.table.date')}</ThCell>
              <ThCell field="fournisseur">{t('executions.results.table.vendor')}</ThCell>
              <ThCell field="montantTtc">{t('executions.results.table.amountTtc')}</ThCell>
              <th className={styles.thStatic}>
                {t('executions.results.table.payment')}
              </th>
              <th className={styles.thStatic}>
                {t('executions.results.table.paidAmount')}
              </th>
              <ThCell field="statut">{t('executions.results.table.status')}</ThCell>
              <ThCell field="scoreConfiance">{t('executions.results.table.confidence')}</ThCell>
              <th className={clsx(styles.thStatic, styles.thRight)}>
                {t('executions.results.table.actions')}
              </th>
            </tr>
          </thead>
          <tbody className={styles.tbody}>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={9} className={styles.emptyCell}>
                  {search || statusFilter !== 'all'
                    ? t('executions.results.noResultsFiltered')
                    : t('executions.results.noResults')}
                </td>
              </tr>
            ) : (
              filtered.map((correlation) => (
                <tr
                  key={correlation.publicId}
                  className={clsx(
                    styles.tr,
                    styles.trBorder,
                    correlation.isManual && styles.trManual
                  )}
                >
                  <td className={clsx(styles.td, styles.tdInvoice)}>
                    <div className={styles.invoiceCell}>
                      {correlation.invoice?.numero ?? '\u2014'}
                      {correlation.isManual && (
                        <PenLine className={styles.editedMark} aria-label={t('executions.correlation.isEdited')} />
                      )}
                    </div>
                  </td>
                  <td className={clsx(styles.td, styles.tdDate)}>
                    {correlation.invoice ? formatDate(correlation.invoice.dateEmission) : '\u2014'}
                  </td>
                  <td className={clsx(styles.td, styles.tdVendor)} title={correlation.invoice?.fournisseur ?? ''}>
                    {correlation.invoice?.fournisseur ?? '\u2014'}
                  </td>
                  <td className={clsx(styles.td, styles.tdMono)}>
                    {correlation.invoice
                      ? formatAmount(parseFloat(correlation.invoice.montantTtc), correlation.invoice.devise)
                      : '\u2014'}
                  </td>
                  <td className={clsx(styles.td, styles.tdMuted)}>
                    {correlation.payment?.reference ?? '\u2014'}
                  </td>
                  <td className={clsx(styles.td, styles.tdMono)}>
                    {correlation.payment
                      ? formatAmount(parseFloat(correlation.payment.montant), correlation.payment.devise)
                      : '\u2014'}
                  </td>
                  <td className={styles.td}>
                    <Badge variant={STATUS_VARIANT[correlation.statut]} dot>
                      {t(`executions.correlationStatus.${correlation.statut}` as Parameters<typeof t>[0])}
                    </Badge>
                  </td>
                  <td className={styles.td}>
                    <div className={styles.confidenceCell}>
                      <div className={styles.miniBar}>
                        <div
                          className={miniBarFillClass(correlation.scoreConfiance)}
                          style={{ width: `${correlation.scoreConfiance}%` }}
                        />
                      </div>
                      <span className={styles.scoreText}>
                        {formatScore(correlation.scoreConfiance)}
                      </span>
                    </div>
                  </td>
                  <td className={styles.actionsCell}>
                    <div className={styles.actionsInner}>
                      <button
                        type="button"
                        onClick={() => { setDetailCorrelation(correlation); setDetailMode('view'); }}
                        className={styles.actionBtn}
                        title={t('executions.results.viewDetails')}
                      >
                        <Eye className={styles.actionIcon} />
                      </button>
                      <button
                        type="button"
                        onClick={() => { setDetailCorrelation(correlation); setDetailMode('edit'); }}
                        className={styles.actionBtn}
                        title={t('executions.results.editCorrelation')}
                      >
                        <Edit3 className={styles.actionIcon} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Row count */}
      {filtered.length > 0 && (
        <p className={styles.rowCount}>
          {filtered.length} r{'\u00e9'}sultat{filtered.length > 1 ? 's' : ''}
          {correlations.length !== filtered.length && ` sur ${correlations.length}`}
        </p>
      )}

      {/* Detail / Edit modal */}
      <CorrelationDetailModal
        correlation={detailCorrelation}
        open={detailCorrelation !== null}
        onClose={() => setDetailCorrelation(null)}
        onSave={onEdit}
      />
    </div>
  );
}
