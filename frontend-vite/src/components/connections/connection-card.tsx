import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { MoreVertical, Plug2, RefreshCw, CheckCircle, AlertTriangle, FileText, Trash2, ExternalLink } from 'lucide-react';
import { clsx } from 'clsx';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ServiceIcon } from './service-icon';
import { formatDate } from '@/lib/utils';
import { getServiceById } from '@/lib/services-catalog';
import type { ServiceConnection } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './connection-card.module.css';
import { Link } from 'react-router-dom';

interface ConnectionCardProps {
  connection: ServiceConnection;
  onDisconnect: (id: string) => Promise<void>;
  onTestConnection: (id: string) => Promise<boolean>;
  onSync: (id: string) => Promise<unknown>;
}

const statusBadgeVariant: Record<ServiceConnection['status'], BadgeVariant> = {
  active: 'success',
  expired: 'warning',
  error: 'error',
  pending: 'default',
};

export function ConnectionCard({
  connection,
  onDisconnect,
  onTestConnection,
  onSync,
}: ConnectionCardProps) {
  const { t } = useTranslation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [isSyncing, setIsSyncing] = useState(false);
  const [isDisconnecting, setIsDisconnecting] = useState(false);
  const [testResult, setTestResult] = useState<boolean | null>(null);
  const [syncResult, setSyncResult] = useState<string | null>(null);

  const service = getServiceById(connection.providerName.toLowerCase());

  const handleTest = async () => {
    setIsTesting(true);
    setMenuOpen(false);
    try {
      const ok = await onTestConnection(connection.publicId);
      setTestResult(ok);
      setTimeout(() => setTestResult(null), 3000);
    } finally {
      setIsTesting(false);
    }
  };

  const handleSync = async () => {
    setIsSyncing(true);
    setMenuOpen(false);
    setSyncResult(null);
    try {
      await onSync(connection.publicId);
      setSyncResult('ok');
      setTimeout(() => setSyncResult(null), 3000);
    } catch {
      setSyncResult('error');
      setTimeout(() => setSyncResult(null), 3000);
    } finally {
      setIsSyncing(false);
    }
  };

  const handleDisconnect = async () => {
    if (!confirm(t('connections.disconnectConfirm', { service: connection.providerName }))) return;
    setIsDisconnecting(true);
    setMenuOpen(false);
    try {
      await onDisconnect(connection.publicId);
    } finally {
      setIsDisconnecting(false);
    }
  };

  const isFileImport = connection.authType === 'file_upload';

  const typeBadgeVariant: Record<string, BadgeVariant> = {
    invoicing: 'info',
    payment: 'default',
    email: 'default',
    banking: 'success',
  };

  return (
    <div className={styles.card}>
      {/* Service icon */}
      <ServiceIcon
        service={service ?? { initials: connection.providerName.slice(0, 2).toUpperCase(), color: '#8A857D', name: connection.providerName }}
        size="md"
      />

      {/* Info */}
      <div className={styles.info}>
        <div className={styles.nameRow}>
          <p className={styles.providerName}>{connection.providerName}</p>
          <Badge variant={typeBadgeVariant[connection.serviceType]}>
            {t(`connections.types.${connection.serviceType}` as Parameters<typeof t>[0])}
          </Badge>
          <Badge variant={statusBadgeVariant[connection.status]} dot>
            {t(`connections.status.${connection.status}` as Parameters<typeof t>[0])}
          </Badge>
        </div>

        <p className={styles.meta}>
          {connection.lastSync
            ? `${t('connections.lastSync')} : ${formatDate(connection.lastSync)}`
            : `${t('connections.connectedOn')} : ${formatDate(connection.createdAt)}`}
        </p>

        {/* Error message */}
        {connection.errorMessage && (
          <p className={styles.errorMsg}>{connection.errorMessage}</p>
        )}

        {/* Test result feedback */}
        {testResult !== null && (
          <p className={clsx(styles.testResult, testResult ? styles.testSuccess : styles.testFailed)}>
            {testResult ? (
              <><CheckCircle className={styles.testIcon} /> {t('connections.testSuccess')}</>
            ) : (
              <><AlertTriangle className={styles.testIcon} /> {t('connections.testFailed')}</>
            )}
          </p>
        )}

        {/* Sync result feedback */}
        {syncResult !== null && (
          <p className={clsx(styles.testResult, syncResult === 'ok' ? styles.testSuccess : styles.testFailed)}>
            {syncResult === 'ok' ? (
              <><CheckCircle className={styles.testIcon} /> Sync OK</>
            ) : (
              <><AlertTriangle className={styles.testIcon} /> Sync failed</>
            )}
          </p>
        )}
      </div>

      {/* Actions */}
      <div className={styles.actions}>
        {/* Context menu */}
        <div className={styles.menuWrap}>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => setMenuOpen(!menuOpen)}
            aria-haspopup="menu"
            aria-expanded={menuOpen}
            aria-label="Options"
          >
            <MoreVertical className={styles.menuBtnIcon} />
          </Button>

          {menuOpen && (
            <>
              <div className={styles.overlay} onClick={() => setMenuOpen(false)} aria-hidden="true" />
              <div className={styles.menu} role="menu">
                {isFileImport ? (
                  <>
                    <Link
                      to="/transactions?source=bank_import"
                      className={styles.menuItem}
                      role="menuitem"
                      onClick={() => setMenuOpen(false)}
                    >
                      <ExternalLink className={styles.menuItemIcon} />
                      Voir les transactions
                    </Link>
                    <div className={styles.menuDivider} />
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleDisconnect}
                      disabled={isDisconnecting}
                      className={clsx(styles.menuItem, styles.menuItemDanger)}
                    >
                      <Trash2 className={styles.menuItemIcon} />
                      Supprimer l'import
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleSync}
                      disabled={isSyncing}
                      className={styles.menuItem}
                    >
                      <RefreshCw className={styles.menuItemIcon} style={isSyncing ? { animation: 'spin 1s linear infinite' } : undefined} />
                      {isSyncing ? 'Sync...' : 'Sync'}
                    </button>
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleTest}
                      disabled={isTesting}
                      className={styles.menuItem}
                    >
                      <Plug2 className={styles.menuItemIcon} />
                      {t('connections.testConnection')}
                    </button>
                    <div className={styles.menuDivider} />
                    <button
                      type="button"
                      role="menuitem"
                      onClick={handleDisconnect}
                      disabled={isDisconnecting}
                      className={clsx(styles.menuItem, styles.menuItemDanger)}
                    >
                      {t('connections.disconnect')}
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
