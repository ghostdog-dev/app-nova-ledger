import { clsx } from 'clsx';
import type { ServiceDefinition } from '@/lib/services-catalog';
import styles from './service-icon.module.css';

interface ServiceIconProps {
  service: Pick<ServiceDefinition, 'initials' | 'color' | 'name'>;
  size?: 'sm' | 'md' | 'lg';
}

const sizeMap = {
  sm: styles.sm,
  md: styles.md,
  lg: styles.lg,
};

export function ServiceIcon({ service, size = 'md' }: ServiceIconProps) {
  return (
    <span
      className={clsx(styles.icon, sizeMap[size])}
      style={{ backgroundColor: service.color }}
      aria-hidden="true"
      title={service.name}
    >
      {service.initials}
    </span>
  );
}
