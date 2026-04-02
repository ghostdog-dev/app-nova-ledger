import { useTranslation } from 'react-i18next';
import { Plus, ArrowRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ServiceIcon } from '@/components/connections/service-icon';
import { getServiceById } from '@/lib/services-catalog';
import type { ServiceConnection } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './services-widget.module.css';
import { Link } from 'react-router-dom';

interface ServicesWidgetProps {
  connections: ServiceConnection[];
  onAddConnection: () => void;
}

const statusVariant: Record<ServiceConnection['status'], BadgeVariant> = {
  active: 'success',
  expired: 'warning',
  error: 'error',
  pending: 'default',
};

export function ServicesWidget({ connections, onAddConnection }: ServicesWidgetProps) {
  const { t } = useTranslation();
  const activeCount = connections.filter((c) => c.status === 'active').length;

  return (
    <Card padding="md">
      <CardHeader>
        <div className={styles.headerRow}>
          <CardTitle>{t('dashboard.connectedServices')}</CardTitle>
          <span className={styles.count}>{connections.length}</span>
        </div>
      </CardHeader>
      <CardContent>
        {connections.length === 0 ? (
          <div className={styles.emptyState}>
            <p className={styles.emptyText}>{t('dashboard.noConnectedServices')}</p>
            <Button size="sm" leftIcon={<Plus className={styles.iconSm} />} onClick={onAddConnection}>
              {t('dashboard.addFirstService')}
            </Button>
          </div>
        ) : (
          <div className={styles.list}>
            {connections.slice(0, 4).map((conn) => {
              const service = getServiceById(conn.providerName.toLowerCase());
              return (
                <div key={conn.publicId} className={styles.serviceRow}>
                  <ServiceIcon
                    service={
                      service ?? {
                        initials: conn.providerName.slice(0, 2).toUpperCase(),
                        color: '#8A857D',
                        name: conn.providerName,
                      }
                    }
                    size="sm"
                  />
                  <span className={styles.serviceName}>
                    {conn.providerName}
                  </span>
                  <Badge variant={statusVariant[conn.status]} dot>
                    {t(`connections.status.${conn.status}` as Parameters<typeof t>[0])}
                  </Badge>
                </div>
              );
            })}

            {connections.length > 4 && (
              <p className={styles.moreText}>
                +{connections.length - 4} autres
              </p>
            )}

            <div className={styles.footer}>
              <button
                type="button"
                onClick={onAddConnection}
                className={styles.footerLink}
              >
                <Plus className={styles.iconXs} /> {t('connections.addConnection')}
              </button>
              <Link to="/connections"
                className={styles.footerLink}
              >
                {t('dashboard.viewAllConnections')} <ArrowRight className={styles.iconXs} />
              </Link>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
