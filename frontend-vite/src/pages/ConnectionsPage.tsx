import { useState, useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { PlusCircle, Link2 } from 'lucide-react';
import { clsx } from 'clsx';
import { Button } from '@/components/ui/button';
import { ConnectionCard } from '@/components/connections/connection-card';
import { AddConnectionModal } from '@/components/connections/add-connection-modal';
import { Alert } from '@/components/ui/alert';
import { Spinner } from '@/components/ui/spinner';
import { useConnections } from '@/hooks/use-connections';
import type { ServiceType } from '@/types';
import styles from './ConnectionsPage.module.css';

type FilterTab = 'all' | ServiceType;

const FILTER_TABS: { value: FilterTab; labelKey: string }[] = [
  { value: 'all', labelKey: 'connections.filterAll' },
  { value: 'invoicing', labelKey: 'connections.filterInvoicing' },
  { value: 'payment', labelKey: 'connections.filterPayment' },
  { value: 'email', labelKey: 'connections.filterEmail' },
  { value: 'banking', labelKey: 'connections.filterBanking' },
];

export default function ConnectionsPage() {
  const { t } = useTranslation();

  const { connections, isLoading, error, refetch, disconnect, test, sync } = useConnections();
  const [filter, setFilter] = useState<FilterTab>('all');
  const [modalOpen, setModalOpen] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  const filtered = filter === 'all' ? connections : connections.filter((c) => c.serviceType === filter);

  const handleDisconnect = useCallback(async (id: string) => {
    await disconnect(id);
  }, [disconnect]);

  const handleTestConnection = useCallback(async (id: string): Promise<boolean> => {
    return test(id);
  }, [test]);

  const handleConnectionAdded = useCallback((serviceId: string) => {
    setModalOpen(false);
    setSuccessMessage(t('connections.disconnectSuccess', { service: serviceId }));
    // Refetch connections from the API
    refetch();
    setTimeout(() => setSuccessMessage(null), 5000);
  }, [t, refetch]);

  const countLabel =
    connections.length === 1
      ? t('connections.connectedCount', { count: 1 })
      : t('connections.connectedCountPlural', { count: connections.length });

  return (
    <>
      <div className={styles.page}>
        {/* Page header */}
        <div className={styles.pageHeaderRow}>
          <div>
            <h1 className={styles.title}>{t('connections.title')}</h1>
            <p className={styles.subtitle}>{t('connections.subtitle')}</p>
          </div>
          <Button
            size="sm"
            leftIcon={<PlusCircle style={{ width: '1rem', height: '1rem' }} />}
            onClick={() => setModalOpen(true)}
          >
            {t('connections.addConnection')}
          </Button>
        </div>

        {/* Success message */}
        {successMessage && (
          <Alert variant="success" onClose={() => setSuccessMessage(null)}>
            {successMessage}
          </Alert>
        )}

        {/* Error */}
        {error && (
          <Alert variant="error" onClose={refetch}>
            {error}
          </Alert>
        )}

        {/* Filter tabs + count */}
        <div className={styles.filterRow}>
          <nav className={styles.filterTabs} aria-label="Filter connections">
            {FILTER_TABS.map(({ value, labelKey }) => (
              <button
                key={value}
                type="button"
                onClick={() => setFilter(value)}
                className={clsx(
                  styles.filterTab,
                  filter === value && styles.filterTabActive
                )}
                aria-current={filter === value ? 'true' : undefined}
              >
                {t(labelKey)}
              </button>
            ))}
          </nav>
          <p className={styles.countText}>{countLabel}</p>
        </div>

        {/* Connection cards */}
        {isLoading ? (
          <div className={styles.loading}>
            <Spinner size="lg" />
          </div>
        ) : filtered.length === 0 ? (
          <div className={styles.emptyState}>
            <Link2 className={styles.emptyIcon} aria-hidden="true" />
            <div>
              <p className={styles.emptyTitle}>{t('connections.noConnections')}</p>
              <p className={styles.emptyDesc}>{t('connections.noConnectionsDescription')}</p>
            </div>
            <Button leftIcon={<PlusCircle style={{ width: '1rem', height: '1rem' }} />} onClick={() => setModalOpen(true)}>
              {t('connections.addConnection')}
            </Button>
          </div>
        ) : (
          <div className={styles.grid}>
            {filtered.map((conn) => (
              <ConnectionCard
                key={conn.publicId}
                connection={conn}
                onDisconnect={handleDisconnect}
                onTestConnection={handleTestConnection}
                onSync={sync}
              />
            ))}
          </div>
        )}

        {/* Service type breakdown */}
        {connections.length > 0 && (
          <div className={styles.breakdownBox}>
            <p className={styles.breakdownLabel}>
              Services par type
            </p>
            <div className={styles.breakdownGrid}>
              {(['invoicing', 'payment', 'email', 'banking'] as ServiceType[]).map((type) => {
                const count = connections.filter((c) => c.serviceType === type).length;
                return (
                  <div key={type}>
                    <p className={styles.breakdownValue}>{count}</p>
                    <p className={styles.breakdownType}>
                      {t(`connections.types.${type}`)}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Add Connection Modal */}
      <AddConnectionModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={handleConnectionAdded}
      />
    </>
  );
}
