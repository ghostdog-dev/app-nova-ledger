import { useState, useCallback, useEffect } from 'react';
import { Loader2, RefreshCw, Database, ChevronLeft, ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';
import { companyApi } from '@/lib/company-api';
import { useConnections, syncConnection } from '@/hooks/use-connections';
import type { ServiceConnection } from '@/types';
import styles from './SourcesPage.module.css';

// ── Types ────────────────────────────────────────────────────────────────────

interface EmailItem {
  id: number;
  subject: string;
  sender: string;
  date: string;
  status: string;
  body_preview: string;
}

interface ConnectionData {
  provider_name: string;
  service_type: string;
  last_sync: string | null;
  items: EmailItem[];
  total_count: number;
  page: number;
  page_size: number;
  total_pages: number;
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

const EMAIL_STATUS_LABELS: Record<string, string> = {
  new: 'Nouveau',
  triage_passed: 'Trie',
  processed: 'Traite',
  ignored: 'Ignore',
};

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
  const isEmailProvider = selectedConnection?.providerName === 'gmail' || selectedConnection?.providerName === 'outlook';

  // Fetch data for selected connection
  const fetchData = useCallback(async () => {
    if (!selectedId) return;
    setIsLoadingData(true);
    try {
      const result = await companyApi.get<ConnectionData>(`/connections/${selectedId}/data/?page=${page}&page_size=50`);
      setData(result);
    } catch {
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
              {data?.last_sync && (
                <span className={styles.lastSync}>{formatLastSync(data.last_sync)}</span>
              )}
            </div>

            {isLoadingData ? (
              <div className={styles.loadingState}>
                <Loader2 className={styles.spinner} />
                Chargement...
              </div>
            ) : !data ? (
              <div className={styles.emptyState}>Aucune donnee</div>
            ) : data.message ? (
              <div className={styles.comingSoon}>
                <span className={styles.comingSoonLabel}>Coming soon</span>
                <span>{data.message}</span>
              </div>
            ) : isEmailProvider ? (
              <>
                {/* Table header */}
                <div className={styles.tableHeader}>
                  <div>Date</div>
                  <div>Expediteur</div>
                  <div>Sujet</div>
                  <div>Statut</div>
                </div>

                {data.items.length === 0 ? (
                  <div className={styles.emptyState}>Aucun email</div>
                ) : (
                  data.items.map((item) => (
                    <div key={item.id} className={styles.rowGroup}>
                      <div className={styles.tableRow}>
                        <div className={styles.dateCol}>{formatDate(item.date)}</div>
                        <div className={styles.senderCol} title={item.sender}>{item.sender}</div>
                        <div className={styles.subjectCol} title={item.subject}>{item.subject}</div>
                        <div className={styles.statusCol}>
                          <span className={cn(styles.statusBadge, getStatusClass(item.status))}>
                            {EMAIL_STATUS_LABELS[item.status] || item.status}
                          </span>
                        </div>
                      </div>
                    </div>
                  ))
                )}
              </>
            ) : (
              <div className={styles.emptyState}>Aucune donnee</div>
            )}

            {/* Footer with pagination */}
            {data && data.total_count > 0 && (
              <div className={styles.tableFooter}>
                <span>
                  {data.total_count.toLocaleString('fr-FR')} element{data.total_count > 1 ? 's' : ''} au total
                </span>
                {data.total_pages > 1 && (
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
                      {page} / {data.total_pages}
                    </span>
                    <button
                      type="button"
                      className={styles.pageBtn}
                      disabled={page >= data.total_pages}
                      onClick={() => setPage((p) => p + 1)}
                    >
                      <ChevronRight size={14} />
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
