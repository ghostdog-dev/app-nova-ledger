import { useState, useEffect, useRef, useCallback } from 'react';
import { getWsTicket } from '@/lib/api-client';
import { companyApi } from '@/lib/company-api';
import type { ExecutionProgress, ExecutionStep, ExecutionStepId, ProgressMessage, ExecutionStatus, ExecutionSummary } from '@/types';

const STEPS_META: { id: ExecutionStepId; label: string }[] = [
  { id: 'triage', label: 'Tri des emails' },
  { id: 'extraction', label: 'Extraction des données' },
  { id: 'merge', label: 'Fusion des transactions' },
  { id: 'computation', label: 'Calculs (TVA, HT, TTC)' },
  { id: 'bank_correlation', label: 'Rapprochement bancaire' },
  { id: 'provider_correlation', label: 'Rapprochement fournisseurs' },
  { id: 'report', label: 'Génération du rapport' },
];

function buildInitialProgress(executionId: string): ExecutionProgress {
  return {
    executionId,
    currentStepIndex: 0,
    totalSteps: STEPS_META.length,
    percentage: 0,
    status: 'running',
    steps: STEPS_META.map((s) => ({ id: s.id, label: s.label, status: 'pending' })),
  };
}

const WS_BASE_URL = (import.meta.env.VITE_WS_URL ?? 'ws://localhost:8000/ws');
const POLLING_INTERVAL_MS = 3000;

interface UseExecutionProgressOptions {
  /** Only connect if execution is currently running */
  enabled?: boolean;
  onCompleted?: (summary: ExecutionSummary) => void;
  onFailed?: (error: string) => void;
}

export function useExecutionProgress(
  executionId: string,
  options: UseExecutionProgressOptions = {}
) {
  const { enabled = true, onCompleted, onFailed } = options;

  const [progress, setProgress] = useState<ExecutionProgress>(() =>
    buildInitialProgress(executionId)
  );
  const [wsConnected, setWsConnected] = useState(false);

  const socketRef = useRef<WebSocket | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const mountedRef = useRef(true);

  /** Apply a progress message to state */
  const applyMessage = useCallback((msg: ProgressMessage) => {
    if (!mountedRef.current) return;

    if (msg.type === 'progress') {
      setProgress((prev) => {
        const steps: ExecutionStep[] = prev.steps.map((s, i) => {
          if (i < msg.stepIndex) return { ...s, status: 'completed' };
          if (i === msg.stepIndex) return { ...s, status: 'running', message: msg.message };
          return s;
        });
        return {
          ...prev,
          currentStepIndex: msg.stepIndex,
          percentage: msg.percentage,
          steps,
          status: 'running',
        };
      });
    }

    if (msg.type === 'completed') {
      setProgress((prev) => ({
        ...prev,
        percentage: 100,
        status: 'completed',
        steps: prev.steps.map((s) => ({ ...s, status: 'completed' })),
      }));
      onCompleted?.(msg.summary);
    }

    if (msg.type === 'failed') {
      setProgress((prev) => ({
        ...prev,
        status: 'failed',
        error: msg.error,
        steps: prev.steps.map((s) =>
          s.status === 'running' ? { ...s, status: 'failed' } : s
        ),
      }));
      onFailed?.(msg.error);
    }
  }, [onCompleted, onFailed]);

  /** Poll the REST endpoint as WebSocket fallback */
  const startPolling = useCallback(() => {
    if (pollingRef.current) return;
    pollingRef.current = setInterval(async () => {
      try {
        const data = await companyApi.get<ProgressMessage>(`/executions/${executionId}/progress/`);
        applyMessage(data);
        if (data.type === 'completed' || data.type === 'failed') {
          clearInterval(pollingRef.current!);
          pollingRef.current = null;
        }
      } catch {
        // Ignore transient network errors
      }
    }, POLLING_INTERVAL_MS);
  }, [executionId, applyMessage]);

  useEffect(() => {
    mountedRef.current = true;
    if (!enabled) return;

    // [F06] Obtain a single-use ticket instead of passing JWT in the URL
    let cancelled = false;
    (async () => {
      const ticket = await getWsTicket();
      if (cancelled) return;

      const wsUrl = `${WS_BASE_URL}/executions/${executionId}/${ticket ? `?ticket=${ticket}` : ''}`;

      let ws: WebSocket;
      try {
        ws = new WebSocket(wsUrl);
        socketRef.current = ws;

        ws.onopen = () => {
          if (mountedRef.current) setWsConnected(true);
        };

        ws.onmessage = (event) => {
          try {
            const msg: ProgressMessage = JSON.parse(event.data as string);
            applyMessage(msg);
          } catch {
            // Ignore malformed messages
          }
        };

        ws.onerror = () => {
          // Fall back to polling if WebSocket fails
          setWsConnected(false);
          startPolling();
        };

        ws.onclose = () => {
          if (mountedRef.current) {
            setWsConnected(false);
            // Start polling if execution may still be running
            startPolling();
          }
        };
      } catch {
        // WebSocket not available, fall back to polling
        startPolling();
      }
    })();

    return () => {
      cancelled = true;
      mountedRef.current = false;
      socketRef.current?.close();
      socketRef.current = null;
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [executionId, enabled, applyMessage, startPolling]);

  return { progress, wsConnected };
}
