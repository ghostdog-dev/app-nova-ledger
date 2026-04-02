import { useState, useCallback, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ArrowUpRight,
  Check,
  AlertTriangle,
  XCircle,
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

interface UnifiedTransaction {
  id: number;
  publicId: string;
  sourceType: string;
  direction: 'inflow' | 'outflow';
  category: string;
  amount: string;
  currency: string;
  amountTaxExcl: string | null;
  taxAmount: string | null;
  taxRate: string | null;
  transactionDate: string;
  vendorName: string;
  description: string;
  reference: string | null;
  paymentMethod: string | null;
  pcgCode: string | null;
  pcgLabel: string | null;
  businessPersonal: string;
  tvaDeductible: boolean;
  cluster: number | null;
  reconciliationStatus: 'matched' | 'pending' | 'orphan';
  accountingScore: number;
  accountingStatus: string;
  missingFields: { name: string; key: string; present: boolean }[];
  clusterLabel: string | null;
  clusterSourcesCount: number;
}

interface Response {
  results: UnifiedTransaction[];
  count: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

type StatusFilter = 'all' | 'matched' | 'pending' | 'orphan';

const SOURCE_COLORS: Record<string, string> = {
  stripe: '#635BFF', mollie: '#FF6B6B', paypal: '#0070BA',
  bank_api: '#10B981', bank_import: '#6366F1', email: '#8B5CF6',
};
const SOURCE_NAMES: Record<string, string> = {
  stripe: 'Stripe', mollie: 'Mollie', paypal: 'PayPal',
  bank_api: 'Banque', bank_import: 'Import CSV', email: 'Email',
};

const PAGE_SIZE = 25;

// ── Data field tags ─────────────────────────────────────────────────────────

function scoreColor(score: number): string {
  if (score >= 80) return '#10B981';
  if (score >= 40) return '#F59E0B';
  return '#EF4444';
}

function DataFieldTags({ fields }: { fields: { name: string; present: boolean }[] }) {
  return (
    <div style={{ display: 'flex', gap: '3px', flexWrap: 'wrap' }}>
      {fields.map((f) => (
        <span key={f.name} style={{
          fontSize: '0.55rem', padding: '1px 4px', borderRadius: '3px',
          background: f.present ? 'rgba(16,185,129,0.15)' : 'rgba(255,255,255,0.05)',
          color: f.present ? '#10B981' : 'rgba(255,255,255,0.25)',
          fontWeight: 500,
        }}>
          {f.name}
        </span>
      ))}
    </div>
  );
}

function CompletionBadge({ score }: { score: number }) {
  const color = scoreColor(score);
  const bg = score >= 70 ? 'rgba(16,185,129,0.15)' : score >= 26 ? 'rgba(245,158,11,0.15)' : 'rgba(239,68,68,0.15)';
  return (
    <span style={{ fontSize: '0.65rem', padding: '2px 6px', borderRadius: '4px', background: bg, color, fontWeight: 600, whiteSpace: 'nowrap' }}>
      {score}%
    </span>
  );
}

function SourceDot({ sourceType }: { sourceType: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
      <span style={{ width: '8px', height: '8px', borderRadius: '50%', background: SOURCE_COLORS[sourceType] ?? '#6B7280', flexShrink: 0 }} />
      <span style={{ fontSize: '0.7rem' }}>{SOURCE_NAMES[sourceType] ?? sourceType}</span>
    </span>
  );
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function TransactionsPage() {
  const { t } = useTranslation();
  const activeCompany = useCompanyStore((s) => s.activeCompany);

  const [data, setData] = useState<Response | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [sourceFilter, setSourceFilter] = useState('all');
  const [directionFilter, setDirectionFilter] = useState('all');
  const [expandedRows, setExpandedRows] = useState<Set<number>>(new Set());

  const toggleRow = (i: number) => {
    setExpandedRows((prev) => { const n = new Set(prev); n.has(i) ? n.delete(i) : n.add(i); return n; });
  };

  const fetchTransactions = useCallback(async () => {
    if (!activeCompany) return;
    setIsLoading(true);
    try {
      const params = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
      if (statusFilter !== 'all') params.set('status', statusFilter);
      if (sourceFilter !== 'all') params.set('source', sourceFilter);
      if (directionFilter !== 'all') params.set('direction', directionFilter);
      const result = await companyApi.get<Response>(`/unified-transactions/?${params}`);
      setData(result);
    } catch { /* silent */ } finally { setIsLoading(false); }
  }, [activeCompany, page, statusFilter, sourceFilter, directionFilter]);

  useEffect(() => { fetchTransactions(); }, [fetchTransactions]);
  useEffect(() => { setExpandedRows(new Set()); }, [page, statusFilter, sourceFilter, directionFilter]);

  const setFilter = (f: StatusFilter) => { setStatusFilter(f); setPage(1); };

  const selectStyle: React.CSSProperties = {
    appearance: 'none', background: 'none', border: '1px solid var(--color-border-light)',
    color: 'var(--color-text-muted)', fontFamily: 'var(--font-mono)', fontSize: '0.625rem',
    textTransform: 'uppercase', letterSpacing: '0.05em', padding: '0.25rem 1.25rem 0.25rem 0.5rem',
    cursor: 'pointer',
    backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='10' viewBox='0 0 24 24' fill='none' stroke='%236B7280' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E")`,
    backgroundRepeat: 'no-repeat', backgroundPosition: 'right 0.35rem center',
  };

  return (
    <div className={styles.page}>
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.title}>Rapport Comptable</h1>
          <p className={styles.subtitle}>Vue unifiée de toutes vos transactions — scoring par ligne</p>
        </div>
      </div>

      <div className={styles.tableContainer}>
        {/* Toolbar */}
        <div className={styles.tableToolbar}>
          <div className={styles.toolbarLeft}>
            <span className={styles.badge}>Live</span>
            <span className={styles.tableTitle}>Transactions unifiées</span>
          </div>
          <div className={styles.toolbarRight}>
            {(['all', 'matched', 'pending', 'orphan'] as StatusFilter[]).map((key) => (
              <button key={key} type="button"
                className={cn(styles.filterBtn, statusFilter === key && styles.filterBtnActive)}
                onClick={() => setFilter(key)}>
                {{ all: 'Tout', matched: '80%+', pending: '40-79%', orphan: '< 40%' }[key]}
              </button>
            ))}
            <select value={sourceFilter} onChange={(e) => { setSourceFilter(e.target.value); setPage(1); }} style={selectStyle}>
              <option value="all">Toutes sources</option>
              <option value="stripe">Stripe</option>
              <option value="mollie">Mollie</option>
              <option value="paypal">PayPal</option>
              <option value="bank_api">Banque</option>
              <option value="bank_import">Import CSV</option>
              <option value="email">Email</option>
            </select>
            <select value={directionFilter} onChange={(e) => { setDirectionFilter(e.target.value); setPage(1); }} style={selectStyle}>
              <option value="all">↕ Tout</option>
              <option value="inflow">↑ Entrées</option>
              <option value="outflow">↓ Sorties</option>
            </select>
            <button type="button" className={styles.filterBtn}><Download size={12} /> Export</button>
          </div>
        </div>

        {/* Table header */}
        <div className={styles.tableHeader}>
          <div>Date</div>
          <div>Fournisseur / Description</div>
          <div className={styles.textRight}>Montant</div>
          <div className={styles.textCenter}>Source</div>
          <div className={styles.textCenter}>Données</div>
          <div className={styles.textRight}>Statut</div>
        </div>

        {/* Body */}
        {isLoading ? (
          <div className={styles.loadingState}><Loader2 className={styles.spinner} /> Chargement...</div>
        ) : !data || data.results.length === 0 ? (
          <div className={styles.emptyRow}>Aucune transaction</div>
        ) : (
          data.results.map((row, i) => {
            const isExpanded = expandedRows.has(i);
            const dirColor = row.direction === 'inflow' ? '#10B981' : '#EF4444';
            const dirArrow = row.direction === 'inflow' ? '↑' : '↓';
            return (
              <div key={row.id} className={styles.rowGroup}>
                <div className={styles.tableRow} onClick={() => toggleRow(i)}>
                  <div className={styles.expandBtn} role="button" tabIndex={0} aria-expanded={isExpanded}
                    onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleRow(i); } }}>
                    <ChevronDown className={cn(styles.expandChevron, isExpanded && styles.expandChevronOpen)} />
                  </div>
                  <div className={styles.primaryCols}>
                    <div className={styles.descCell}>
                      <span style={{ color: dirColor, fontWeight: 700, marginRight: '4px' }}>{dirArrow}</span>
                      {row.vendorName || row.description || '—'}
                      <ArrowUpRight size={14} className={styles.arrowIcon} />
                    </div>
                    <div className={styles.dateCell}>{row.transactionDate || '—'}</div>
                    <div className={styles.amountCell}>
                      <span style={{ color: dirColor }}>
                        {row.direction === 'outflow' ? '-' : '+'}{row.amount || '?'} {row.currency}
                      </span>
                    </div>
                  </div>
                  <div className={styles.secondaryCols}>
                    <div className={styles.sourceCell}><SourceDot sourceType={row.sourceType} /></div>
                  </div>
                  {/* Data fields + score */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: '160px' }}>
                    <DataFieldTags fields={row.missingFields} />
                  </div>
                  <div className={styles.statusCell}>
                    <CompletionBadge score={row.accountingScore} />
                  </div>
                </div>

                {/* Expanded detail */}
                <div className={cn(styles.expandedDetail, isExpanded && styles.expandedDetailOpen)}>
                  <div className={styles.expandedDetailInner}>
                    {/* Data completeness */}
                    <div className={styles.detailRow}>
                      <span>Complétude</span>
                      <span style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                        <CompletionBadge score={row.accountingScore} />
                        <DataFieldTags fields={row.missingFields} />
                      </span>
                    </div>
                    {/* Cluster */}
                    {row.clusterLabel && (
                      <div className={styles.detailRow}>
                        <span>Rapprochement</span>
                        <span>{row.clusterLabel} ({row.clusterSourcesCount} source{row.clusterSourcesCount > 1 ? 's' : ''})</span>
                      </div>
                    )}
                    {/* Comptabilité */}
                    {row.pcgCode && (
                      <div className={styles.detailRow}>
                        <span>Code PCG</span>
                        <span>{row.pcgCode}{row.pcgLabel ? ` — ${row.pcgLabel}` : ''}</span>
                      </div>
                    )}
                    <div className={styles.detailRow}>
                      <span>TVA déductible</span>
                      <span>{row.tvaDeductible ? 'Oui' : 'Non'}</span>
                    </div>
                    {(row.taxAmount || row.taxRate) && (
                      <div className={styles.detailRow}>
                        <span>TVA</span>
                        <span>{row.taxAmount ? `${row.taxAmount} ${row.currency}` : ''}{row.taxRate ? ` (${row.taxRate}%)` : ''}</span>
                      </div>
                    )}
                    {row.amountTaxExcl && (
                      <div className={styles.detailRow}>
                        <span>Montant HT</span>
                        <span>{row.amountTaxExcl} {row.currency}</span>
                      </div>
                    )}
                    {/* Détails */}
                    <div className={styles.detailRow}>
                      <span>Catégorie</span>
                      <span>{row.category}</span>
                    </div>
                    {row.reference && (
                      <div className={styles.detailRow}>
                        <span>Référence</span>
                        <span>{row.reference}</span>
                      </div>
                    )}
                    {row.paymentMethod && (
                      <div className={styles.detailRow}>
                        <span>Moyen de paiement</span>
                        <span>{row.paymentMethod}</span>
                      </div>
                    )}
                    <div className={styles.detailRow}>
                      <span>Source</span>
                      <span><SourceDot sourceType={row.sourceType} /></span>
                    </div>
                  </div>
                </div>
              </div>
            );
          })
        )}

        {/* Pagination */}
        {data && (
          <div className={styles.tableFooter}>
            <span>{data.count.toLocaleString('fr-FR')} transaction{data.count > 1 ? 's' : ''}</span>
            <div className={styles.pagination}>
              <button type="button" className={styles.pageBtn} disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                <ChevronLeft size={14} />
              </button>
              <span className={styles.pageInfo}>{page} / {data.totalPages}</span>
              <button type="button" className={styles.pageBtn} disabled={page >= data.totalPages} onClick={() => setPage((p) => p + 1)}>
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
