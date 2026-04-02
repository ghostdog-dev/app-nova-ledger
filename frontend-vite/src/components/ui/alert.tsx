import { HTMLAttributes } from 'react';
import { clsx } from 'clsx';
import { AlertCircle, CheckCircle, Info, TriangleAlert, X } from 'lucide-react';
import type { AlertVariant } from '@/types';
import styles from './alert.module.css';

interface AlertProps extends HTMLAttributes<HTMLDivElement> {
  variant?: AlertVariant;
  title?: string;
  onClose?: () => void;
}

const variantConfig: Record<
  AlertVariant,
  { containerClass: string; icon: React.ComponentType<{ className?: string }>; iconClass: string }
> = {
  info: {
    containerClass: styles.info,
    icon: Info,
    iconClass: styles.iconInfo,
  },
  success: {
    containerClass: styles.success,
    icon: CheckCircle,
    iconClass: styles.iconSuccess,
  },
  warning: {
    containerClass: styles.warning,
    icon: TriangleAlert,
    iconClass: styles.iconWarning,
  },
  error: {
    containerClass: styles.error,
    icon: AlertCircle,
    iconClass: styles.iconError,
  },
};

export function Alert({ variant = 'info', title, onClose, className, children, ...props }: AlertProps) {
  const config = variantConfig[variant];
  const Icon = config.icon;

  return (
    <div
      role="alert"
      className={clsx(
        styles.alert,
        config.containerClass,
        className
      )}
      {...props}
    >
      <Icon className={clsx(styles.icon, config.iconClass)} aria-hidden="true" />
      <div className={styles.content}>
        {title && <p className={styles.title}>{title}</p>}
        <div>{children}</div>
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          className={styles.closeBtn}
          aria-label="Close"
        >
          <X className={styles.closeIcon} />
        </button>
      )}
    </div>
  );
}
