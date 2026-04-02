import { HTMLAttributes } from 'react';
import { clsx } from 'clsx';
import type { BadgeVariant } from '@/types';
import styles from './badge.module.css';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
  dot?: boolean;
}

const variantMap: Record<BadgeVariant, string> = {
  default: styles.default,
  success: styles.success,
  warning: styles.warning,
  error: styles.error,
  info: styles.info,
};

const dotMap: Record<BadgeVariant, string> = {
  default: styles.dotDefault,
  success: styles.dotSuccess,
  warning: styles.dotWarning,
  error: styles.dotError,
  info: styles.dotInfo,
};

export function Badge({ variant = 'default', dot = false, className, children, ...props }: BadgeProps) {
  return (
    <span
      className={clsx(
        styles.badge,
        variantMap[variant],
        className
      )}
      {...props}
    >
      {dot && (
        <span className={clsx(styles.dot, dotMap[variant])} aria-hidden="true" />
      )}
      {children}
    </span>
  );
}
