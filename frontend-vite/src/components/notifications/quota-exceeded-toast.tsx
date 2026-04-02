/**
 * Listens for 'quota-exceeded' custom events emitted by the API client
 * and adds a notification to the global store.
 * Renders nothing — side-effect only.
 */

import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { useNotificationStore } from '@/stores/notification-store';
import type { QuotaExceededDetail } from '@/types';
import styles from './quota-exceeded-toast.module.css';
import { useNavigate } from 'react-router-dom';

export function QuotaExceededListener() {
  const { addNotification } = useNotificationStore();
  const { t } = useTranslation();

  useEffect(() => {
    const handler = (e: Event) => {
      const detail = (e as CustomEvent<Partial<QuotaExceededDetail>>).detail;
      addNotification({
        type: 'quota_exceeded',
        title: t('quota.exceeded'),
        message: detail.resource
          ? t('detail', { resource: detail.resource, current: detail.current ?? 0, max: detail.max ?? 0 })
          : t('quota.exceeded'),
      });
    };

    window.addEventListener('quota-exceeded', handler);
    return () => window.removeEventListener('quota-exceeded', handler);
  }, [addNotification, t]);

  return null;
}

/** Clickable toast content for quota errors — shown in the notification panel */
export function QuotaUpgradeLink() {
  const { t } = useTranslation();
  const navigate = useNavigate();

  return (
    <button
      type="button"
      onClick={() => navigate('/settings/plans')}
      className={styles.upgradeLink}
    >
      {t('quota.upgradeLink')} &rarr;
    </button>
  );
}
