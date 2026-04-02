import { useTranslation } from 'react-i18next';
import { Check, Loader2, X, Circle, Wifi, WifiOff } from 'lucide-react';
import { clsx } from 'clsx';
import type { ExecutionProgress, ExecutionStep } from '@/types';
import styles from './execution-progress.module.css';

interface ExecutionProgressBarProps {
  progress: ExecutionProgress;
  wsConnected: boolean;
}

function StepIcon({ status }: { status: ExecutionStep['status'] }) {
  if (status === 'completed') return <Check className={styles.stepIcon} />;
  if (status === 'running') return <Loader2 className={styles.stepIcon} style={{ animation: 'spin 1s linear infinite' }} />;
  if (status === 'failed') return <X className={styles.stepIcon} />;
  return <Circle className={styles.stepIcon} style={{ opacity: 0.3 }} />;
}

export function ExecutionProgressBar({ progress, wsConnected }: ExecutionProgressBarProps) {
  const { t } = useTranslation();

  return (
    <div className={styles.wrap}>
      {/* Global progress bar */}
      <div>
        <div className={styles.progressHeader}>
          <span className={styles.progressLabel}>{t('executions.progress.title')}</span>
          <div className={styles.progressMeta}>
            {wsConnected ? (
              <span className={clsx(styles.wsStatus, styles.wsConnected)}>
                <Wifi className={styles.wsIcon} /> {t('executions.progress.wsConnected')}
              </span>
            ) : (
              <span className={clsx(styles.wsStatus, styles.wsDisconnected)}>
                <WifiOff className={styles.wsIcon} /> {t('executions.progress.wsPolling')}
              </span>
            )}
            <span className={styles.pctText}>{progress.percentage}%</span>
          </div>
        </div>
        <div className={styles.barTrack}>
          <div
            className={clsx(
              styles.barFill,
              progress.status === 'failed' ? styles.barFillFailed : styles.barFillNormal
            )}
            style={{ width: `${progress.percentage}%` }}
            role="progressbar"
            aria-valuenow={progress.percentage}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
      </div>

      {/* Steps */}
      <ol className={styles.stepList} aria-label="Execution steps">
        {progress.steps.map((step, index) => {
          const isLast = index === progress.steps.length - 1;
          return (
            <li key={step.id} className={styles.step}>
              {/* Vertical connector line */}
              <div className={styles.stepTrack}>
                <span
                  className={clsx(
                    styles.stepCircle,
                    step.status === 'completed' && styles.stepCircleCompleted,
                    step.status === 'running' && styles.stepCircleRunning,
                    step.status === 'failed' && styles.stepCircleFailed,
                    step.status === 'pending' && styles.stepCirclePending
                  )}
                  aria-hidden="true"
                >
                  <StepIcon status={step.status} />
                </span>
                {!isLast && (
                  <span
                    className={clsx(
                      styles.stepConnector,
                      step.status === 'completed' ? styles.stepConnectorDone : styles.stepConnectorPending
                    )}
                    aria-hidden="true"
                  />
                )}
              </div>

              {/* Label + message */}
              <div className={clsx(styles.stepContent, isLast && styles.stepContentLast)}>
                <p className={clsx(
                  styles.stepLabel,
                  step.status === 'completed' && styles.stepLabelCompleted,
                  step.status === 'running' && styles.stepLabelRunning,
                  step.status === 'failed' && styles.stepLabelFailed,
                  step.status === 'pending' && styles.stepLabelPending
                )}>
                  {t(`steps.${step.id}` as Parameters<typeof t>[0])}
                </p>
                {step.message && step.status === 'running' && (
                  <p className={styles.stepMessage}>{step.message}</p>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
