import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bell, CheckCheck, CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { clsx } from 'clsx';
import { useNotificationStore, type AppNotification, type NotificationType } from '@/stores/notification-store';
import styles from './notification-bell.module.css';

const TYPE_ICON: Record<NotificationType, React.ReactNode> = {
  execution_completed: <CheckCircle2 className={clsx(styles.itemIcon, styles.itemIconCompleted)} />,
  execution_failed: <XCircle className={clsx(styles.itemIcon, styles.itemIconFailed)} />,
  token_expired: <AlertTriangle className={clsx(styles.itemIcon, styles.itemIconWarning)} />,
  anomaly_detected: <Info className={clsx(styles.itemIcon, styles.itemIconInfo)} />,
  quota_exceeded: <AlertTriangle className={clsx(styles.itemIcon, styles.itemIconQuota)} />,
};

function timeAgo(iso: string): string {
  const diff = (Date.now() - new Date(iso).getTime()) / 1000;
  if (diff < 60) return 'à l\'instant';
  if (diff < 3600) return `${Math.floor(diff / 60)} min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)} h`;
  return `${Math.floor(diff / 86400)} j`;
}

function NotificationItem({ notification, onDismiss }: { notification: AppNotification; onDismiss: (id: string) => void }) {
  const { markRead } = useNotificationStore();

  return (
    <div
      className={clsx(styles.item, !notification.read && styles.itemUnread)}
      onClick={() => markRead(notification.id)}
    >
      <div className={styles.itemIconWrap}>{TYPE_ICON[notification.type]}</div>
      <div className={styles.itemContent}>
        <p className={clsx(styles.itemTitle, !notification.read && styles.itemTitleUnread)}>
          {notification.title}
        </p>
        <p className={styles.itemMessage}>{notification.message}</p>
        <p className={styles.itemTime}>{timeAgo(notification.createdAt)}</p>
      </div>
      <button
        type="button"
        onClick={(e) => { e.stopPropagation(); onDismiss(notification.id); }}
        className={styles.dismissBtn}
      >
        <X className={styles.dismissIcon} />
      </button>
    </div>
  );
}

export function NotificationBell() {
  const { t } = useTranslation();
  const { notifications, unreadCount, markAllRead, dismiss } = useNotificationStore();
  const [open, setOpen] = useState(false);

  return (
    <div className={styles.wrap}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={styles.bellBtn}
        aria-label={t('notifications.title')}
        aria-expanded={open}
        aria-haspopup="dialog"
      >
        <Bell className={styles.bellIcon} aria-hidden="true" />
        {unreadCount > 0 && (
          <span className={styles.badge}>
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div
            className={styles.overlay}
            onClick={() => setOpen(false)}
            aria-hidden="true"
          />
          <div
            className={styles.dropdown}
            role="dialog"
            aria-label={t('notifications.title')}
          >
            {/* Header */}
            <div className={styles.dropdownHeader}>
              <p className={styles.dropdownTitle}>{t('notifications.title')}</p>
              {unreadCount > 0 && (
                <button
                  type="button"
                  onClick={markAllRead}
                  className={styles.markAllBtn}
                >
                  <CheckCheck className={styles.markAllIcon} />
                  {t('notifications.markAllRead')}
                </button>
              )}
            </div>

            {/* List */}
            <div className={styles.list}>
              {notifications.length === 0 ? (
                <p className={styles.empty}>{t('notifications.empty')}</p>
              ) : (
                notifications.slice(0, 20).map((n) => (
                  <NotificationItem key={n.id} notification={n} onDismiss={dismiss} />
                ))
              )}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
