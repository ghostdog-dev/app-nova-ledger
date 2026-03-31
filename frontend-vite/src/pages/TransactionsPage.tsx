import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowUpRight,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Download,
  Loader2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { companyApi } from '@/lib/company-api';
import { useCompanyStore } from '@/stores/company-store';
import styles from './TransactionsPage.module.css';

// ── Types ────────────────────────────────────────────────────────────────────

type SourceType = 'stripe' | 'mollie' | 'paypal' | 'bank_api' | 'bank_import' | 'email' | string;
type Direction = 'inflow' | 'outflow';
type ReconciliationStatus = 'matched' | 'pending' | 'orphan';

interface UnifiedTransaction {
  id: number;
  publicId: string;
  sourceType: SourceType;
  sourceId: string;
  evidenceRole: string;
  direction: Direction;
  category: string;
  amount: string;
  currency: string;
  transactionDate: string;
  vendorName: string;
  description: string;
  reference: string | null;
  paymentMethod: string | null;
  confidence: number;
  completeness: string;
  pcgCode: string | null;
  pcgLabel: string | null;
  businessPersonal: string;
  tvaDeductible: boolean;
  cluster: number | null;
  reconciliationStatus: ReconciliationStatus;
  createdAt: string;
}

interface UnifiedTransactionsResponse {
  results: UnifiedTransaction[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

type StatusFilter = 'all' | 'matched' | 'pending' | 'orphan';
type SourceFilter = 'all' | SourceType;
type DirectionFilter = 'all' | 'inflow' | 'outflow';

const STATUS_LABELS: Record<string, string> = {
  matched: 'Reconcilie',
  pending: 'En attente',
  orphan: 'Orphelin',
};

const FILTER_LABELS: Record<StatusFilter, string> = {
  all: 'Tout',
  matched: 'Reconcilie',
  pending: 'En attente',
  orphan: 'Orphelin',
};

const SOURCE_OPTIONS: { value: SourceFilter; label: string }[] = [
  { value: 'all', label: 'Toutes sources' },
  { value: 'stripe', label: 'Stripe' },
  { value: 'mollie', label: 'Mollie' },
  { value: 'paypal', label: 'PayPal' },
  { value: 'bank_api', label: 'Banque API' },
  { value: 'bank_import', label: 'Import bancaire' },
  { value: 'email', label: 'Email' },
];

const DIRECTION_OPTIONS: { value: DirectionFilter; label: string }[] = [
  { value: 'all', label: 'Toutes directions' },
  { value: 'inflow', label: '↑ Entrees' },
  { value: 'outflow', label: '↓ Sorties' },
];

const CATEGORY_OPTIONS: { value: string; label: string }[] = [
  { value: 'all', label: 'Toutes categories' },
  { value: 'revenue', label: 'Revenu' },
  { value: 'expense_service', label: 'Charge — Service' },
  { value: 'expense_supply', label: 'Charge — Fourniture' },
  { value: 'expense_travel', label: 'Charge — Deplacement' },
  { value: 'tax', label: 'Taxe' },
  { value: 'transfer', label: 'Virement interne' },
  { value: 'other', label: 'Autre' },
];

const SOURCE_COLORS: Record<string, string> = {
  stripe: '#635BFF',
  mollie: '#FF6B6B',
  paypal: '#0070BA',
  bank_api: '#10B981',
  bank_import: '#6366F1',
  email: '#8B5CF6',
};

const SOURCE_DISPLAY_NAMES: Record<string, string> = {
  stripe: 'Stripe',
  mollie: 'Mollie',
  paypal: 'PayPal',
  bank_api: 'Banque API',
  bank_import: 'Import',
  email: 'Email',
};

const PAGE_SIZE = 20;

function getSourceColor(sourceType: string): string {
  return SOURCE_COLORS[sourceType] ?? '#6B7280';
}

function getSourceDisplayName(sourceType: string): string {
  return SOURCE_DISPLAY_NAMES[sourceType] ?? sourceType;
}

function formatConfidence(confidence: number): string {
  return `${Math.round(confidence * 100)}%`;
}

// ── Inline select style (to avoid modifying CSS module) ─────────────────────

const selectStyle: React.CSSProperties = {
  appearance: 'none',
  WebkitAppearance: 'none',
  background: 'none',
  border: '1px solid var(--color-border-light)',
  color: 'var(--color-text-muted)',
  fontFamily: 'var(--font-mono)',
  fontSize: '0.625rem',
  lineHeight: '1rem',
  textTransform: 'uppercase',
  letterSpacing: '0.05em',
  padding: '0.25rem 1.25rem 0.25rem 0.5rem',
  cursor: 'pointer',
  backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
  backgroundRepeat: 'no-repeat',
  backgroundPosition: 'right 0.35rem center',
};

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TransactionsPage() {
  const { t } = useTranslation();
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const [data, setData] = useState<UnifiedTransactionsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all');
  const [directionFilter, setDirectionFilter] = useState<DirectionFilter>('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleRow = (index: number) => {
    setExpandedRows((prev) => {
      const next = new Set(prev);
      if (next.has(index)) next.delete(index);
      else next.add(index);
      return next;
    });
  };

  const fetchTransactions = useCallback(async () => {
    if (!activeCompany) return;
    setIsLoading(true);
    try {
      const params = new URLSearchParams({
        page: String(page),
        page_size: String(PAGE_SIZE),
      });
      if (statusFilter !== 'all') {
        params.set('status', statusFilter);
      }
      if (sourceFilter !== 'all') {
        params.set('source', sourceFilter);
      }
      if (directionFilter !== 'all') {
        params.set('direction', directionFilter);
      }
      if (categoryFilter !== 'all') {
        params.set('category', categoryFilter);
      }
      const result = await companyApi.get<UnifiedTransactionsResponse>(
        `/unified-transactions/?${params.toString()}`
      );
      setData(result);
    } catch {
      // Silently handle — the user already sees the dashboard data
    } finally {
      setIsLoading(false);
    }
  }, [activeCompany, page, statusFilter, sourceFilter, directionFilter, categoryFilter]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  // Collapse expanded rows on page/filter change
  useEffect(() => {
    setExpandedRows(new Set());
  }, [page, statusFilter, sourceFilter, directionFilter, categoryFilter]);

  const handleFilterChange = (filter: StatusFilter) => {
    setStatusFilter(filter);
    setPage(1);
  };

  const handleSourceChange = (value: string) => {
    setSourceFilter(value as SourceFilter);
    setPage(1);
  };

  const handleDirectionChange = (value: string) => {
    setDirectionFilter(value as DirectionFilter);
    setPage(1);
  };

  const handleCategoryChange = (value: string) => {
    setCategoryFilter(value);
    setPage(1);
  };

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.title}>{t('transactions.title')}</h1>
          <p className={styles.subtitle}>{t('transactions.subtitle')}</p>
        </div>
      </div>

      {/* Dark table */}
      <div className={styles.tableContainer}>
        {/* Toolbar */}
        <div className={styles.tableToolbar}>
          <div className={styles.toolbarLeft}>
            <span className={styles.badge}>Live</span>
            <span className={styles.tableTitle}>{t('transactions.tableTitle')}</span>
          </div>
          <div className={styles.toolbarRight}>
            {/* Status filters */}
            {(Object.keys(FILTER_LABELS) as StatusFilter[]).map((key) => (
              <button
                key={key}
                type="button"
                className={cn(
                  styles.filterBtn,
                  statusFilter === key && styles.filterBtnActive
                )}
                onClick={() => handleFilterChange(key)}
              >
                {FILTER_LABELS[key]}
              </button>
            ))}

            {/* Source filter dropdown */}
            <select
              value={sourceFilter}
              onChange={(e) => handleSourceChange(e.target.value)}
              style={selectStyle}
            >
              {SOURCE_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            {/* Direction filter dropdown */}
            <select
              value={directionFilter}
              onChange={(e) => handleDirectionChange(e.target.value)}
              style={selectStyle}
            >
              {DIRECTION_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            {/* Category filter dropdown */}
            <select
              value={categoryFilter}
              onChange={(e) => handleCategoryChange(e.target.value)}
              style={selectStyle}
            >
              {CATEGORY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>

            <span className={styles.liveIndicator}>
              <span className={styles.liveDot} />
              Connecte
            </span>
            <button type="button" className={styles.filterBtn}>
              <Download size={12} /> Export
            </button>
          </div>
        </div>

        {/* Table header (desktop only, shown via CSS) */}
        <div className={styles.tableHeader}>
          <div>Date</div>
          <div>Description</div>
          <div className={styles.textRight}>Montant</div>
          <div className={styles.textCenter}>Source</div>
          <div className={styles.textRight}>Statut</div>
        </div>

        {/* Table body */}
        {isLoading ? (
          <div className={styles.loadingState}>
            <Loader2 className={styles.spinner} />
            Chargement...
          </div>
        ) : !data || data.results.length === 0 ? (
          <div className={styles.emptyRow}>Aucune transaction</div>
        ) : (
          data.results.map((row, i) => {
            const isExpanded = expandedRows.has(i);
            const sourceColor = getSourceColor(row.sourceType);
            const directionArrow = row.direction === 'inflow' ? '↑' : '↓';
            const directionColor = row.direction === 'inflow' ? '#10B981' : '#EF4444';
            return (
              <div key={row.id} className={styles.rowGroup}>
                {/* Main row */}
                <div className={styles.tableRow} onClick={() => toggleRow(i)}>
                  {/* Expand button (mobile) */}
                  <div
                    className={styles.expandBtn}
                    role="button"
                    tabIndex={0}
                    aria-expanded={isExpanded}
                    aria-label="Expand row details"
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        toggleRow(i);
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

                  {/* Primary columns (always visible) */}
                  <div className={styles.primaryCols}>
                    <div className={styles.descCell}>
                      <span style={{ color: directionColor, fontWeight: 700, marginRight: '0.25rem' }}>
                        {directionArrow}
                      </span>
                      {row.vendorName || row.description}
                      <ArrowUpRight size={14} className={styles.arrowIcon} />
                    </div>
                    <div className={styles.dateCell}>{row.transactionDate}</div>
                    <div className={styles.amountCell}>
                      <span style={{ color: directionColor }}>
                        {row.direction === 'outflow' ? '-' : '+'}{row.amount} {row.currency}
                      </span>
                    </div>
                  </div>

                  {/* Secondary columns (desktop only, shown via CSS) */}
                  <div className={styles.secondaryCols}>
                    <div className={styles.sourceCell}>
                      <span className={styles.sourceTag} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: sourceColor,
                            flexShrink: 0,
                          }}
                        />
                        {getSourceDisplayName(row.sourceType)}
                      </span>
                    </div>
                  </div>

                  {/* Status (always visible) */}
                  <div className={styles.statusCell}>
                    <span
                      className={cn(
                        styles.statusBadge,
                        row.reconciliationStatus === 'matched' && styles.badgeMatched,
                        row.reconciliationStatus === 'pending' && styles.badgePending,
                        row.reconciliationStatus === 'orphan' && styles.badgeOrphan,
                      )}
                    >
                      {row.reconciliationStatus === 'matched' ? <Check size={10} /> : null}
                      {STATUS_LABELS[row.reconciliationStatus]}
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
                    <div className={styles.detailRow}>
                      <span>Source</span>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.375rem' }}>
                        <span
                          style={{
                            display: 'inline-block',
                            width: '8px',
                            height: '8px',
                            borderRadius: '50%',
                            backgroundColor: sourceColor,
                          }}
                        />
                        {getSourceDisplayName(row.sourceType)}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span>Direction</span>
                      <span style={{ color: directionColor }}>
                        {directionArrow} {row.direction === 'inflow' ? 'Entree' : 'Sortie'}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span>Date</span>
                      <span>{row.transactionDate}</span>
                    </div>
                    <div className={styles.detailRow}>
                      <span>Montant</span>
                      <span style={{ color: directionColor }}>
                        {row.direction === 'outflow' ? '-' : '+'}{row.amount} {row.currency}
                      </span>
                    </div>
                    <div className={styles.detailRow}>
                      <span>Statut</span>
                      <span>{STATUS_LABELS[row.reconciliationStatus]}</span>
                    </div>
                    <div className={styles.detailRow}>
                      <span>Categorie</span>
                      <span>{row.category}</span>
                    </div>
                    {row.pcgCode && (
                      <div className={styles.detailRow}>
                        <span>Code PCG</span>
                        <span>{row.pcgCode}{row.pcgLabel ? ` — ${row.pcgLabel}` : ''}</span>
                      </div>
                    )}
                    <div className={styles.detailRow}>
                      <span>Confiance</span>
                      <span>{formatConfidence(row.confidence)}</span>
                    </div>
                    {row.reference && (
                      <div className={styles.detailRow}>
                        <span>Reference</span>
                        <span>{row.reference}</span>
                      </div>
                    )}
                    {row.cluster != null && (
                      <div className={styles.detailRow}>
                        <span>Cluster</span>
                        <span>#{row.cluster}</span>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            );
          })
        )}

        {/* Footer / Pagination */}
        {data && (
          <div className={styles.tableFooter}>
            <span>
              {data.count.toLocaleString('fr-FR')} transaction{data.count > 1 ? 's' : ''} au total
            </span>
            <div className={styles.pagination}>
              <button
                type="button"
                className={styles.pageBtn}
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                <ChevronLeft size={14} />
              </button>
              <span className={styles.pageInfo}>
                {page} / {data.totalPages}
              </span>
              <button
                type="button"
                className={styles.pageBtn}
                disabled={page >= data.totalPages}
                onClick={() => setPage((p) => p + 1)}
              >
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
