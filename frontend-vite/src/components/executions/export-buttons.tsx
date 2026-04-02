import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Download, ChevronDown } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { requestExport } from '@/hooks/use-executions';
import { apiClient } from '@/lib/api-client';
import type { ExportFormat, ExportFile } from '@/types';
import styles from './export-buttons.module.css';

interface ExportButtonsProps {
  executionId: string | number;
}

const FORMATS: { format: ExportFormat; icon: string }[] = [
  { format: 'csv', icon: '\uD83D\uDCC4' },
  { format: 'excel', icon: '\uD83D\uDCCA' },
  { format: 'pdf', icon: '\uD83D\uDCD5' },
  { format: 'json', icon: '{ }' },
];

const POLL_INTERVAL_MS = 2000;
const MAX_POLL_ATTEMPTS = 30;

/**
 * F52 — Allowed origins for export download URLs.
 * Only URLs starting with the API origin or the current page origin are permitted.
 */
const ALLOWED_DOWNLOAD_ORIGINS: string[] = [
  import.meta.env.VITE_API_ORIGIN ?? 'http://localhost:8000',
  typeof window !== 'undefined' ? window.location.origin : '',
].filter(Boolean);

/**
 * F52 — Validate that a file URL is from a trusted origin.
 * Rejects external URLs to prevent open-redirect / data exfiltration attacks.
 */
function isAllowedDownloadUrl(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    // Only allow http(s) protocols
    if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') {
      return false;
    }
    // Allow relative URLs (same origin) and URLs matching allowed origins
    return ALLOWED_DOWNLOAD_ORIGINS.some((origin) => parsed.origin === new URL(origin).origin);
  } catch {
    return false;
  }
}

export function ExportButtons({ executionId }: ExportButtonsProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [downloading, setDownloading] = useState<ExportFormat | null>(null);

  const handleExport = async (format: ExportFormat) => {
    setOpen(false);
    setDownloading(format);
    try {
      // Step 1: Request export creation via POST
      const exportFile = await requestExport(executionId, format);

      // Step 2: If file is already ready, download immediately
      if (exportFile.status === 'ready' && exportFile.fileUrl) {
        downloadFile(exportFile);
        return;
      }

      // Step 3: Poll until the export is ready
      // (export generation is async via Celery)
      let attempts = 0;
      const poll = async () => {
        // We re-fetch by hitting the exports list endpoint filtered
        // For simplicity, we use the returned file URL once ready
        // The backend returns the export file object
        if (attempts >= MAX_POLL_ATTEMPTS) {
          throw new Error('Export timed out');
        }
        attempts++;
        // Wait before polling
        await new Promise((r) => setTimeout(r, POLL_INTERVAL_MS));

        const updated = await apiClient.get<ExportFile>(`/exports/${exportFile.id}/`);

        if (updated.status === 'ready' && updated.fileUrl) {
          downloadFile(updated);
          return;
        }
        if (updated.status === 'error') {
          throw new Error(updated.errorMessage || 'Export failed');
        }
        // Still generating, poll again
        await poll();
      };

      await poll();
    } catch {
      // TODO: show error toast
    } finally {
      setDownloading(null);
    }
  };

  const downloadFile = (exportFile: ExportFile) => {
    // F52 — Validate the download URL before using it
    if (!isAllowedDownloadUrl(exportFile.fileUrl)) {
      console.error('Export download blocked: untrusted URL origin');
      return;
    }

    const a = document.createElement('a');
    a.href = exportFile.fileUrl;
    a.download = exportFile.originalFilename || `export-${executionId}.${exportFile.format === 'excel' ? 'xlsx' : exportFile.format}`;
    a.click();
  };

  return (
    <div className={styles.wrap}>
      <Button
        variant="secondary"
        size="sm"
        onClick={() => setOpen(!open)}
        isLoading={downloading !== null}
        leftIcon={<Download className={styles.downloadIcon} />}
        rightIcon={<ChevronDown className={styles.chevronIcon} />}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <span className={styles.btnLabel}>
          {downloading ? t('executions.export.downloading') : 'Exporter'}
        </span>
      </Button>

      {open && (
        <>
          <div className={styles.overlay} onClick={() => setOpen(false)} aria-hidden="true" />
          <div
            className={styles.menu}
            role="menu"
          >
            {FORMATS.map(({ format, icon }) => (
              <button
                key={format}
                type="button"
                role="menuitem"
                onClick={() => handleExport(format)}
                className={styles.menuItem}
              >
                <span className={styles.menuItemIcon} aria-hidden="true">{icon}</span>
                {t(`executions.export.${format}`)}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
