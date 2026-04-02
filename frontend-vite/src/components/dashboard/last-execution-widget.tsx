import { useTranslation } from 'react-i18next';
import { clsx } from 'clsx';
import { PlaySquare, CheckCircle, XCircle, Clock, ArrowRight } from 'lucide-react';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { formatDate, formatScore } from '@/lib/utils';
import type { Execution } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './last-execution-widget.module.css';
import { Link } from 'react-router-dom';

interface LastExecutionWidgetProps {
  execution: Execution | null;
  onStartNew: () => void;
}

const statusBadgeVariant: Record<Execution['status'], BadgeVariant> = {
  pending: 'default',
  running: 'info',
  completed: 'success',
  failed: 'error',
};

const StatusIcon = ({ status }: { status: Execution['status'] }) => {
  if (status === 'completed') return <CheckCircle className={clsx(styles.iconSm, styles.statusIconGreen)} />;
  if (status === 'failed') return <XCircle className={clsx(styles.iconSm, styles.statusIconRed)} />;
  if (status === 'running') return <Clock className={clsx(styles.iconSm, styles.statusIconPulse)} />;
  return <Clock className={clsx(styles.iconSm, styles.statusIconMuted)} />;
};

export function LastExecutionWidget({ execution, onStartNew }: LastExecutionWidgetProps) {
  const { t } = useTranslation();

  return (
    <Card padding="md">
      <CardHeader>
        <div className={styles.headerRow}>
          <CardTitle>{t('dashboard.lastExecution')}</CardTitle>
          <Button size="sm" leftIcon={<PlaySquare className={styles.iconSm} />} onClick={onStartNew}>
            {t('dashboard.startExecution')}
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        {!execution ? (
          <div className={styles.emptyState}>
            <PlaySquare className={styles.emptyIcon} aria-hidden="true" />
            <div>
              <p className={styles.emptyTitle}>{t('dashboard.noExecution')}</p>
              <p className={styles.emptyDesc}>{t('dashboard.noExecutionDescription')}</p>
            </div>
          </div>
        ) : (
          <div className={styles.content}>
            {/* Status + date */}
            <div className={styles.statusRow}>
              <StatusIcon status={execution.status} />
              <Badge variant={statusBadgeVariant[execution.status]}>
                {t(`executions.status.${execution.status}` as Parameters<typeof t>[0])}
              </Badge>
              <span className={styles.statusDate}>
                {formatDate(execution.createdAt)}
              </span>
            </div>

            {/* Progress bar (running only) */}
            {execution.status === 'running' && (
              <div className={styles.progressWrap}>
                <p className={styles.progressLabel}>{t('dashboard.executionProgress')}</p>
                <div className={styles.progressBar}>
                  <div className={styles.progressFill} />
                </div>
              </div>
            )}

            {/* Summary (completed) */}
            {execution.status === 'completed' && execution.summary && (
              <div className={styles.summaryGrid}>
                <div className={styles.summaryBox}>
                  <p className={clsx(styles.summaryValue, styles.summaryValueDefault)}>
                    {execution.summary.invoicesProcessed}
                  </p>
                  <p className={styles.summaryLabel}>{t('dashboard.invoicesProcessed')}</p>
                </div>
                <div className={styles.summaryBox}>
                  <p className={clsx(styles.summaryValue, styles.summaryValueGreen)}>
                    {execution.summary.correlationsFound}
                  </p>
                  <p className={styles.summaryLabel}>{t('dashboard.correlationsFound')}</p>
                </div>
                <div className={styles.summaryBox}>
                  <p className={clsx(styles.summaryValue, styles.summaryValueAmber)}>
                    {execution.summary.anomaliesDetected}
                  </p>
                  <p className={styles.summaryLabel}>{t('dashboard.anomaliesFound')}</p>
                </div>
              </div>
            )}

            {/* Period */}
            <p className={styles.period}>
              {t('executions.period')} :{' '}
              {formatDate(execution.dateFrom)} → {formatDate(execution.dateTo)}
            </p>

            {execution.status === 'completed' && (
              <Link to={`/executions/${execution.publicId}`}
                className={styles.viewLink}
              >
                {t('executions.viewResults')} <ArrowRight className={styles.iconXs} />
              </Link>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
