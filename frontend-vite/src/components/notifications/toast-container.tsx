import { useEffect } from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Info, X } from 'lucide-react';
import { clsx } from 'clsx';
import { useNotificationStore, type AppNotification, type NotificationType } from '@/stores/notification-store';
import styles from './toast-container.module.css';

const TOAST_DURATION_MS = 5000;

const ICONS: Record<NotificationType, React.ReactNode> = {
  execution_completed: <CheckCircle2 className={clsx(styles.toastIcon, styles.toastIconCompleted)} />,
  execution_failed: <XCircle className={clsx(styles.toastIcon, styles.toastIconFailed)} />,
  token_expired: <AlertTriangle className={clsx(styles.toastIcon, styles.toastIconWarning)} />,
  anomaly_detected: <Info className={clsx(styles.toastIcon, styles.toastIconInfo)} />,
  quota_exceeded: <AlertTriangle className={clsx(styles.toastIcon, styles.toastIconQuota)} />,
};

function Toast({ notification }: { notification: AppNotification }) {
  const { dequeueToast } = useNotificationStore();

  useEffect(() => {
    const t = setTimeout(() => dequeueToast(notification.id), TOAST_DURATION_MS);
    return () => clearTimeout(t);
  }, [notification.id, dequeueToast]);

  return (
    <div
      className={styles.toast}
      role="alert"
    >
      {ICONS[notification.type]}
      <div className={styles.toastContent}>
        <p className={styles.toastTitle}>{notification.title}</p>
        <p className={styles.toastMessage}>{notification.message}</p>
      </div>
      <button
        type="button"
        onClick={() => dequeueToast(notification.id)}
        className={styles.toastClose}
      >
        <X className={styles.toastCloseIcon} />
      </button>
    </div>
  );
}

export function ToastContainer() {
  const { toastQueue } = useNotificationStore();

  if (toastQueue.length === 0) return null;

  return (
    <div
      className={styles.container}
      aria-live="polite"
      aria-label="Notifications"
    >
      {toastQueue.map((n) => (
        <Toast key={n.id} notification={n} />
      ))}
    </div>
  );
}
