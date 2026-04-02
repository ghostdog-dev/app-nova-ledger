/**
 * Global WebSocket listener for system-wide notifications.
 * Mounts once in the app layout; connects to the notifications endpoint
 * and dispatches events to the Zustand notification store.
 */

import { useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { getStoredAccessToken, getWsTicket } from '@/lib/api-client';
import { useNotificationStore } from '@/stores/notification-store';

type ServerNotificationMessage =
  | { type: 'execution_completed'; execution_id: string; title?: string; message?: string }
  | { type: 'execution_failed'; execution_id: string; error?: string }
  | { type: 'token_expired'; service?: string }
  | { type: 'anomaly_detected'; execution_id?: string; count?: number };

const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws';

/** F68 — Exponential backoff configuration for WebSocket reconnection. */
const WS_MAX_RETRIES = 5;
const WS_BASE_DELAY_MS = 1000;
const WS_MAX_DELAY_MS = 30000;

export function NotificationListener() {
  const { addNotification } = useNotificationStore();
  const { t } = useTranslation();
  const socketRef = useRef<WebSocket | null>(null);
  const reconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const mountedRef = useRef(true);
  /** F68 — Track reconnection attempts for exponential backoff. */
  const retryCountRef = useRef(0);

  useEffect(() => {
    mountedRef.current = true;

    async function connect() {
      if (!mountedRef.current) return;
      // Quick check: if no access token in memory, user is not authenticated
      const token = getStoredAccessToken();
      if (!token) return;

      // [F06] Obtain a single-use ticket instead of passing JWT in the URL
      const ticket = await getWsTicket();
      if (!mountedRef.current || !ticket) return;

      try {
        const ws = new WebSocket(
          `${WS_BASE_URL}/notifications/?ticket=${ticket}`
        );
        socketRef.current = ws;

        ws.onopen = () => {
          // F68 — Reset retry counter on successful connection
          retryCountRef.current = 0;
        };

        ws.onmessage = (event) => {
          try {
            const msg: ServerNotificationMessage = JSON.parse(event.data as string);
            switch (msg.type) {
              case 'execution_completed':
                addNotification({
                  type: 'execution_completed',
                  title: t('types.execution_completed'),
                  message: msg.message ?? t('types.execution_completed'),
                  executionId: msg.execution_id,
                });
                break;
              case 'execution_failed':
                addNotification({
                  type: 'execution_failed',
                  title: t('types.execution_failed'),
                  message: msg.error ?? t('types.execution_failed'),
                  executionId: msg.execution_id,
                });
                break;
              case 'token_expired':
                addNotification({
                  type: 'token_expired',
                  title: t('types.token_expired'),
                  message: msg.service
                    ? `${msg.service} — ${t('types.token_expired').toLowerCase()}`
                    : t('types.token_expired'),
                });
                break;
              case 'anomaly_detected':
                addNotification({
                  type: 'anomaly_detected',
                  title: t('types.anomaly_detected'),
                  message: msg.count ? `${msg.count} anomalie${msg.count > 1 ? 's' : ''}` : t('types.anomaly_detected'),
                  executionId: msg.execution_id,
                });
                break;
            }
          } catch {
            // Ignore malformed messages
          }
        };

        ws.onclose = () => {
          // F68 — Exponential backoff with jitter and retry limit
          if (mountedRef.current && retryCountRef.current < WS_MAX_RETRIES) {
            const delay = Math.min(
              WS_BASE_DELAY_MS * Math.pow(2, retryCountRef.current),
              WS_MAX_DELAY_MS
            ) + Math.random() * 1000;
            retryCountRef.current += 1;
            reconnectRef.current = setTimeout(() => { connect(); }, delay);
          } else if (retryCountRef.current >= WS_MAX_RETRIES) {
            console.warn('NotificationListener: max WebSocket reconnection attempts reached');
          }
        };

        ws.onerror = () => {
          ws.close();
        };
      } catch {
        // WebSocket unavailable (SSR or unsupported env)
      }
    }

    connect();

    return () => {
      mountedRef.current = false;
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
      socketRef.current?.close();
    };
  }, [addNotification, t]);

  return null;
}
