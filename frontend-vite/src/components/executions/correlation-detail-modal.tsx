import { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { X, Edit3, AlertTriangle, PenLine } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert } from '@/components/ui/alert';
import { formatAmount, formatDate, formatScore } from '@/lib/utils';
import type { Correlation, CorrelationStatus, CorrelationUpdatePayload } from '@/types';
import type { BadgeVariant } from '@/types';
import styles from './correlation-detail-modal.module.css';

interface CorrelationDetailModalProps {
  correlation: Correlation | null;
  open: boolean;
  onClose: () => void;
  onSave: (id: string, patch: CorrelationUpdatePayload) => Promise<void>;
}

const statusVariant: Record<CorrelationStatus, BadgeVariant> = {
  reconciled: 'success',
  reconciled_with_alert: 'warning',
  unpaid: 'error',
  orphan_payment: 'error',
  uncertain: 'default',
};

function ConfidenceBar({ score }: { score: number }) {
  const barClass = score >= 90 ? styles.barFillGreen : score >= 70 ? styles.barFillAmber : styles.barFillRed;
  return (
    <div className={styles.confidenceBar}>
      <div className={styles.barTrack}>
        <div className={barClass} style={{ width: `${score}%` }} />
      </div>
      <span className={styles.barScore}>{formatScore(score)}</span>
    </div>
  );
}

function DetailRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className={styles.detailRow}>
      <span className={styles.detailLabel}>{label}</span>
      <span className={styles.detailValue}>{value ?? '\u2014'}</span>
    </div>
  );
}

export function CorrelationDetailModal({ correlation, open, onClose, onSave }: CorrelationDetailModalProps) {
  const { t } = useTranslation();

  const [isEditing, setIsEditing] = useState(false);
  const [notes, setNotes] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (correlation) {
      setNotes(correlation.notes ?? '');
    }
    setIsEditing(false);
    setError(null);
  }, [correlation]);

  useEffect(() => {
    if (!open) return;
    const handleEsc = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('keydown', handleEsc);
    return () => document.removeEventListener('keydown', handleEsc);
  }, [open, onClose]);

  if (!open || !correlation) return null;

  const handleSave = async () => {
    setIsSaving(true);
    setError(null);
    try {
      await onSave(correlation.publicId, {
        notes: notes || undefined,
        isManual: true,
      });
      setIsEditing(false);
    } catch {
      setError(t('errors.unknown'));
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className={styles.overlay} role="dialog" aria-modal="true">
      <div className={styles.backdrop} onClick={onClose} aria-hidden="true" />

      <div className={styles.panel}>
        {/* Header */}
        <div className={styles.header}>
          <div className={styles.headerLeft}>
            <h2 className={styles.headerTitle}>
              {t('executions.correlation.detailTitle')}
            </h2>
            {correlation.isManual && (
              <Badge variant="info">
                <PenLine className={styles.editedIcon} />
                {t('executions.correlation.isEdited')}
              </Badge>
            )}
          </div>
          <button type="button" onClick={onClose} className={styles.closeBtn}>
            <X className={styles.closeIcon} />
          </button>
        </div>

        <div className={styles.body}>
          {/* Status + confidence */}
          <div className={styles.section}>
            <div className={styles.statusRow}>
              <Badge variant={statusVariant[correlation.statut]} dot>
                {t(`executions.correlationStatus.${correlation.statut}` as Parameters<typeof t>[0])}
              </Badge>
              <div className={styles.confidenceWrap}>
                <p className={styles.confidenceLabel}>{t('executions.results.table.confidence')}</p>
                <ConfidenceBar score={correlation.scoreConfiance} />
              </div>
            </div>
          </div>

          {/* Invoice section */}
          <div className={styles.section}>
            <p className={styles.sectionLabel}>
              {t('executions.correlation.invoiceSection')}
            </p>
            <DetailRow label={t('executions.results.table.invoice')} value={correlation.invoice?.numero} />
            <DetailRow label={t('executions.results.table.date')} value={correlation.invoice?.dateEmission ? formatDate(correlation.invoice.dateEmission) : null} />
            <DetailRow label={t('executions.results.table.vendor')} value={correlation.invoice?.fournisseur} />
            <DetailRow label={t('executions.results.table.amountHt')} value={correlation.invoice ? formatAmount(parseFloat(correlation.invoice.montantHt), correlation.invoice.devise) : null} />
            <DetailRow label={t('executions.results.table.amountTtc')} value={correlation.invoice ? formatAmount(parseFloat(correlation.invoice.montantTtc), correlation.invoice.devise) : null} />
          </div>

          {/* Payment section */}
          <div className={styles.section}>
            <p className={styles.sectionLabel}>
              {t('executions.correlation.paymentSection')}
            </p>
            <DetailRow label={t('executions.results.table.payment')} value={correlation.payment?.reference} />
            <DetailRow label={t('executions.results.table.paymentDate')} value={correlation.payment?.date ? formatDate(correlation.payment.date) : null} />
            <DetailRow label={t('executions.results.table.paidAmount')} value={correlation.payment ? formatAmount(parseFloat(correlation.payment.montant), correlation.payment.devise) : null} />
            <DetailRow label={t('executions.results.table.method')} value={correlation.payment?.methode} />
          </div>

          {/* Anomalies section */}
          {correlation.anomalies && correlation.anomalies.length > 0 && (
            <div className={styles.section}>
              <p className={styles.sectionLabel}>
                Anomalies
              </p>
              <div className={styles.anomalyList}>
                {correlation.anomalies.map((anomaly) => (
                  <div key={anomaly.publicId} className={styles.anomalyItem}>
                    <AlertTriangle className={styles.anomalyIcon} />
                    <div>
                      <p className={styles.anomalyType}>{anomaly.type}</p>
                      <p className={styles.anomalyDesc}>{anomaly.description}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Match criteria */}
          {correlation.matchCriteria && (
            <div className={styles.section}>
              <DetailRow label="Crit\u00e8res de matching" value={correlation.matchCriteria} />
            </div>
          )}

          {/* Edit section */}
          {isEditing ? (
            <div className={styles.section}>
              <div className={styles.editSection}>
                <p className={styles.editHint}>{t('executions.correlation.editHint')}</p>
                {error && <Alert variant="error" onClose={() => setError(null)}>{error}</Alert>}
                <div className={styles.editLabelWrap}>
                  <label className={styles.editLabel}>
                    Notes{' '}
                    <span className={styles.editLabelOptional}>({t('common.optional')})</span>
                  </label>
                  <textarea
                    className={styles.editTextarea}
                    rows={3}
                    placeholder={t('executions.correlation.annotationPlaceholder')}
                    value={notes}
                    onChange={(e) => setNotes(e.target.value)}
                  />
                </div>
                <div className={styles.editActions}>
                  <Button isLoading={isSaving} onClick={handleSave}>
                    {t('executions.correlation.saveEdit')}
                  </Button>
                  <Button variant="ghost" onClick={() => setIsEditing(false)}>
                    {t('executions.correlation.cancelEdit')}
                  </Button>
                </div>
              </div>
            </div>
          ) : (
            <div className={styles.section}>
              <div className={styles.viewSection}>
                {correlation.notes && (
                  <p className={styles.noteText}>&ldquo;{correlation.notes}&rdquo;</p>
                )}
                <div className={styles.editBtnWrap}>
                  <Button
                    variant="secondary"
                    size="sm"
                    leftIcon={<Edit3 className={styles.editIcon} />}
                    onClick={() => setIsEditing(true)}
                  >
                    {t('executions.results.editCorrelation')}
                  </Button>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
