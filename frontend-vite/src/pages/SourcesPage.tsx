import { useState, useCallback, useEffect } from 'react';
import { Loader2, RefreshCw, Database, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { companyApi } from '@/lib/company-api';
import { useConnections, syncConnection } from '@/hooks/use-connections';
import type { ServiceConnection } from '@/types';
import styles from './SourcesPage.module.css';

// ── Types ────────────────────────────────────────────────────────────────────

interface DataItem {
  id: number;
  // Email fields
  subject?: string;
  sender?: string;
  bodyPreview?: string;
  // Payment fields
  description?: string;
  amount?: number;
  currency?: string;
  fee?: number;
  net?: number;
  type?: string;
  // Common
  date: string;
  status: string;
}

interface ConnectionData {
  providerName: string;
  serviceType: string;
  lastSync: string | null;
  items: DataItem[];
  columns?: string[];
  totalCount: number;
  page: number;
  pageSize: number;
  totalPages: number;
  message?: string;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

const PROVIDER_LABELS: Record<string, string> = {
  gmail: 'Gmail',
  outlook: 'Outlook',
  stripe: 'Stripe',
  paypal: 'PayPal',
  gocardless: 'GoCardless',
  pennylane: 'Pennylane',
  qonto: 'Qonto',
  shopify: 'Shopify',
  woocommerce: 'WooCommerce',
  prestashop: 'PrestaShop',
  sumup: 'SumUp',
  payplug: 'PayPlug',
  fintecture: 'Fintecture',
  evoliz: 'Evoliz',
  vosfactures: 'VosFactures',
  choruspro: 'Chorus Pro',
};

function getProviderLabel(name: string): string {
  return PROVIDER_LABELS[name] || name.charAt(0).toUpperCase() + name.slice(1);
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit', year: '2-digit' });
}

function formatLastSync(iso: string | null): string {
  if (!iso) return 'Jamais synchronise';
  const d = new Date(iso);
  return `Derniere sync : ${d.toLocaleDateString('fr-FR')} ${d.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' })}`;
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Nouveau', triage_passed: 'Trie', processed: 'Traite', ignored: 'Ignore',
  succeeded: 'OK', pending: 'En attente', failed: 'Echoue', available: 'Disponible',
  paid: 'Paye', open: 'Ouvert', canceled: 'Annule', refunded: 'Rembourse',
  completed: 'Termine', active: 'Actif', expired: 'Expire',
  COMPLETED: 'Termine', DENIED: 'Refuse', PENDING: 'En attente',
  SUCCESSFUL: 'OK', FAILED: 'Echoue',
};

const COLUMN_LABELS: Record<string, string> = {
  date: 'Date', sender: 'Expediteur', subject: 'Sujet', status: 'Statut',
  description: 'Description', amount: 'Montant', fee: 'Frais', net: 'Net',
  method: 'Methode', side: 'Sens', installments: 'Echeances', currency: 'Devise',
  type: 'Type',
};

const AMOUNT_COLS = new Set(['amount', 'fee', 'net', 'installments']);
function isAmountCol(col: string) { return AMOUNT_COLS.has(col); }

function formatAmount(val: unknown): string {
  if (val === null || val === undefined) return '-';
  const n = Number(val);
  if (isNaN(n)) return String(val);
  return n.toLocaleString('fr-FR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function gridCols(columns: string[]): string {
  return columns.map((col) => {
    if (col === 'date') return '7rem';
    if (col === 'subject' || col === 'description') return '1fr';
    if (col === 'sender') return '12rem';
    if (AMOUNT_COLS.has(col)) return '6rem';
    return '5rem';
  }).join(' ');
}

function getStatusClass(status: string): string {
  switch (status) {
    case 'new':
      return styles.badgeNew;
    case 'processed':
    case 'triage_passed':
      return styles.badgeProcessed;
    case 'ignored':
      return styles.badgeIgnored;
    default:
      return styles.badgeProcessed;
  }
}

function getStatusDotClass(status: string): string {
  switch (status) {
    case 'active':
      return styles.statusDotActive;
    case 'error':
      return styles.statusDotError;
    default:
      return styles.statusDotPending;
  }
}

// ── Page ─────────────────────────────────────────────────────────────────────

export default function SourcesPage() {
  const { connections, isLoading: connectionsLoading } = useConnections();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [data, setData] = useState<ConnectionData | null>(null);
  const [isLoadingData, setIsLoadingData] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [page, setPage] = useState(1);

  // Auto-select first connection
  useEffect(() => {
    if (!selectedId && connections.length > 0) {
      setSelectedId(connections[0].publicId);
    }
  }, [connections, selectedId]);

  const selectedConnection = connections.find((c) => c.publicId === selectedId);

  // Fetch data for selected connection
  const fetchData = useCallback(async () => {
    if (!selectedId) return;
    setIsLoadingData(true);
    try {
      const url = `/connections/${selectedId}/data/?page=${page}&page_size=50`;
      console.log('[Sources] fetching', url);
      const result = await companyApi.get<ConnectionData>(url);
      console.log('[Sources] result', { totalCount: result.totalCount, items: result.items?.length, page: result.page, totalPages: result.totalPages });
      setData(result);
    } catch (err) {
      console.error('[Sources] fetch error', err);
      setData(null);
    } finally {
      setIsLoadingData(false);
    }
  }, [selectedId, page]);

  useEffect(() => {
    if (selectedId) {
      fetchData();
    }
  }, [selectedId, fetchData]);

  // Sync handler
  const handleSync = async () => {
    if (!selectedId) return;
    setIsSyncing(true);
    try {
      await syncConnection(selectedId);
      await fetchData();
    } catch {
      // silent
    } finally {
      setIsSyncing(false);
    }
  };

  const handleTabClick = (conn: ServiceConnection) => {
    setSelectedId(conn.publicId);
    setPage(1);
    setData(null);
  };

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.title}>Sources</h1>
          <p className={styles.subtitle}>Donnees importees par vos connexions</p>
        </div>
      </div>

      {/* Tabs + Sync button */}
      {connectionsLoading ? (
        <div className={styles.loadingState}>
          <Loader2 className={styles.spinner} />
          Chargement...
        </div>
      ) : connections.length === 0 ? (
        <div className={styles.emptyState}>Aucune connexion configuree</div>
      ) : (
        <>
          <div className={styles.tabsBar}>
            {connections.map((conn) => (
              <button
                key={conn.publicId}
                type="button"
                className={cn(styles.tab, selectedId === conn.publicId && styles.tabActive)}
                onClick={() => handleTabClick(conn)}
              >
                <span className={cn(styles.statusDot, getStatusDotClass(conn.status))} />
                {getProviderLabel(conn.providerName)}
              </button>
            ))}
            <button
              type="button"
              className={styles.syncBtn}
              onClick={handleSync}
              disabled={!selectedId || isSyncing}
            >
              <RefreshCw size={12} className={isSyncing ? styles.spinner : undefined} />
              {isSyncing ? 'Sync...' : 'Sync'}
            </button>
          </div>

          {/* Data table */}
          <div className={styles.tableContainer}>
            {/* Toolbar */}
            <div className={styles.tableToolbar}>
              <div className={styles.toolbarLeft}>
                <Database size={16} style={{ color: 'var(--color-text-light)' }} />
                <span className={styles.tableTitle}>
                  {selectedConnection ? getProviderLabel(selectedConnection.providerName) : 'Source'}
                </span>
              </div>
              {data?.lastSync && (
                <span className={styles.lastSync}>{formatLastSync(data.lastSync)}</span>
              )}
            </div>

            {isLoadingData ? (
              <div className={styles.loadingState}>
                <Loader2 className={styles.spinner} />
                Chargement...
              </div>
            ) : !data ? (
              <div className={styles.emptyState}>Aucune donnee</div>
            ) : data.items.length === 0 ? (
              <div className={styles.emptyState}>Aucune donnee — lancez une synchronisation</div>
            ) : (
              <>
                {/* Dynamic table header */}
                <div className={styles.tableHeader} style={{ gridTemplateColumns: gridCols(data.columns || []) }}>
                  {(data.columns || []).map((col) => (
                    <div key={col} className={isAmountCol(col) ? styles.textRight : undefined}>
                      {COLUMN_LABELS[col] || col}
                    </div>
                  ))}
                </div>

                {/* Dynamic rows */}
                {data.items.map((item) => (
                  <div key={item.id} className={styles.rowGroup}>
                    <div className={styles.tableRow} style={{ gridTemplateColumns: gridCols(data.columns || []) }}>
                      {(data.columns || []).map((col) => (
                        <div key={col} className={cn(isAmountCol(col) && styles.textRight, col === 'status' && styles.statusCol)}>
                          {col === 'date' ? formatDate(item.date) :
                           col === 'status' ? (
                            <span className={cn(styles.statusBadge, getStatusClass(item.status))}>
                              {STATUS_LABELS[item.status] || item.status}
                            </span>
                           ) :
                           isAmountCol(col) ? formatAmount(item[col as keyof DataItem]) :
                           String(item[col as keyof DataItem] ?? '')}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </>
            )}

            {/* Footer with pagination */}
            {data && (
              <div className={styles.tableFooter}>
                <span>
                  {data.totalCount.toLocaleString('fr-FR')} element{data.totalCount > 1 ? 's' : ''} au total
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
                    {page} / {data.totalPages || 1}
                  </span>
                  <button
                    type="button"
                    className={styles.pageBtn}
                    disabled={page >= (data.totalPages || 1)}
                    onClick={() => setPage((p) => p + 1)}
                  >
                    <ChevronRight size={14} />
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
