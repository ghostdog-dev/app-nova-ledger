import { useTranslation } from 'react-i18next';
import { AlertTriangle, Clock, Zap, CheckCircle } from 'lucide-react';
import { clsx } from 'clsx';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import styles from './alerts-widget.module.css';

export interface DashboardAlert {
  id: string;
  type: 'token_expired' | 'anomaly' | 'execution_failed' | 'connection_error' | 'info';
  message: string;
  serviceName?: string;
  createdAt: string;
  read: boolean;
}

interface AlertsWidgetProps {
  alerts: DashboardAlert[];
  onDismiss?: (id: string) => void;
}

const alertIconMap: Record<string, { Icon: typeof Clock; style: string }> = {
  token_expired: { Icon: Clock, style: styles.alertIconAmber },
  anomaly: { Icon: AlertTriangle, style: styles.alertIconRed },
  execution_failed: { Icon: Zap, style: styles.alertIconRed },
  connection_error: { Icon: Zap, style: styles.alertIconRed },
  info: { Icon: CheckCircle, style: styles.alertIconBlue },
};

export function AlertsWidget({ alerts, onDismiss }: AlertsWidgetProps) {
  const { t } = useTranslation();
  const unreadCount = alerts.filter((a) => !a.read).length;

  return (
    <Card padding="md">
      <CardHeader>
        <div className={styles.headerRow}>
          <CardTitle>{t('dashboard.alerts')}</CardTitle>
          {unreadCount > 0 && (
            <Badge variant="error">{unreadCount}</Badge>
          )}
        </div>
      </CardHeader>
      <CardContent>
        {alerts.length === 0 ? (
          <div className={styles.emptyState}>
            <CheckCircle className={styles.emptyIcon} aria-hidden="true" />
            <p className={styles.emptyText}>{t('dashboard.noAlerts')}</p>
          </div>
        ) : (
          <ul className={styles.alertList} role="list">
            {alerts.map((alert) => {
              const { Icon, style: iconStyle } = alertIconMap[alert.type];
              return (
                <li
                  key={alert.id}
                  className={clsx(
                    styles.alertItem,
                    alert.read ? styles.alertItemRead : styles.alertItemUnread
                  )}
                >
                  <Icon className={clsx(styles.alertIcon, iconStyle)} aria-hidden="true" />
                  <div className={styles.alertBody}>
                    <p className={clsx(styles.alertMessage, !alert.read && styles.alertMessageUnread)}>
                      {alert.message}
                    </p>
                    {alert.serviceName && (
                      <p className={styles.alertService}>{alert.serviceName}</p>
                    )}
                  </div>
                  {onDismiss && !alert.read && (
                    <button
                      type="button"
                      onClick={() => onDismiss(alert.id)}
                      className={styles.dismissBtn}
                      aria-label="Dismiss"
                    >
                      ✕
                    </button>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
