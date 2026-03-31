import { useState, useCallback, useEffect, useRef } from 'react';
import { Upload, FileText, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { companyApi } from '@/lib/company-api';
import { getStoredAccessToken } from '@/lib/api-client';
import { useCompanyStore } from '@/stores/company-store';
import styles from './BankImportPage.module.css';

// ── Types ────────────────────────────────────────────────────────────────────

interface UploadResult {
  status: string;
  importId: number;
  bankName: string;
  rowsTotal: number;
  rowsImported: number;
  rowsSkipped: number;
  dateRange: [string, string];
  warnings: string[];
}

interface BankImport {
  id: number;
  createdAt: string;
  bankName: string;
  fileType: string;
  status: string;
  rowsImported: number;
  dateRange: [string, string] | null;
}

interface BankImportListResponse {
  results: BankImport[];
  count: number;
}

const ACCEPTED_EXTENSIONS = '.csv,.ofx,.qfx,.xml';
const ACCEPTED_TYPES = [
  'text/csv',
  'application/x-ofx',
  'application/x-qfx',
  'text/xml',
  'application/xml',
];

// ── Page ─────────────────────────────────────────────────────────────────────

export default function BankImportPage() {
  const activeCompany = useCompanyStore((s) => s.activeCompany);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Upload state
  const [isDragOver, setIsDragOver] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadResult | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);

  // History state
  const [imports, setImports] = useState<BankImport[]>([]);
  const [historyCount, setHistoryCount] = useState(0);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);

  // ── Fetch history ──────────────────────────────────────────────────────────

  const fetchHistory = useCallback(async () => {
    if (!activeCompany) return;
    setIsLoadingHistory(true);
    try {
      const data = await companyApi.get<BankImportListResponse>('/bank-import/');
      setImports(data.results);
      setHistoryCount(data.count);
    } catch {
      // silently handle
    } finally {
      setIsLoadingHistory(false);
    }
  }, [activeCompany]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // ── Upload logic ───────────────────────────────────────────────────────────

  const uploadFile = useCallback(
    async (file: File) => {
      if (!activeCompany) return;

      setIsUploading(true);
      setUploadResult(null);
      setUploadError(null);

      try {
        const formData = new FormData();
        formData.append('file', file);

        const apiBaseUrl = import.meta.env.VITE_API_URL ?? '/api/v1';
        const url = `${apiBaseUrl}/companies/${activeCompany.publicId}/bank-import/upload/`;

        const headers: Record<string, string> = {};
        const accessToken = getStoredAccessToken();
        if (accessToken) {
          headers['Authorization'] = `Bearer ${accessToken}`;
        }

        const response = await fetch(url, {
          method: 'POST',
          headers,
          credentials: 'include',
          body: formData,
        });

        if (!response.ok) {
          let msg = `Upload failed (${response.status})`;
          try {
            const err = await response.json();
            if (err.detail) msg = err.detail;
          } catch {
            // ignore
          }
          setUploadError(msg);
          return;
        }

        const result: UploadResult = await response.json();
        setUploadResult(result);
        // Refresh history
        fetchHistory();
      } catch {
        setUploadError('Network error — could not reach server.');
      } finally {
        setIsUploading(false);
      }
    },
    [activeCompany, fetchHistory],
  );

  const handleFileSelect = (files: FileList | null) => {
    if (!files || files.length === 0) return;
    uploadFile(files[0]);
  };

  // ── Drag & drop handlers ──────────────────────────────────────────────────

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    handleFileSelect(e.dataTransfer.files);
  };

  const handleClick = () => {
    fileInputRef.current?.click();
  };

  // ── Helpers ────────────────────────────────────────────────────────────────

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString('fr-FR');
    } catch {
      return iso;
    }
  };

  const formatPeriod = (dateRange: [string, string] | null) => {
    if (!dateRange) return '—';
    return `${formatDate(dateRange[0])} — ${formatDate(dateRange[1])}`;
  };

  const statusBadgeClass = (status: string) => {
    if (status === 'imported') return styles.badgeImported;
    if (status === 'failed') return styles.badgeFailed;
    return styles.badgeProcessing;
  };

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className={styles.page}>
      {/* Page header */}
      <div className={styles.pageHeaderRow}>
        <div>
          <h1 className={styles.title}>Import bancaire</h1>
          <p className={styles.subtitle}>
            Importez vos releves CSV, OFX, QFX ou XML
          </p>
        </div>
      </div>

      {/* Upload zone */}
      {isUploading ? (
        <div className={styles.uploadLoading}>
          <Loader2 className={styles.spinner} />
          Import en cours...
        </div>
      ) : (
        <div
          className={cn(
            styles.uploadZone,
            isDragOver && styles.uploadZoneActive,
          )}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={handleClick}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ' ') {
              e.preventDefault();
              handleClick();
            }
          }}
        >
          <Upload size={32} className={styles.uploadIcon} />
          <div className={styles.uploadTitle}>
            Glissez un fichier ici ou cliquez pour parcourir
          </div>
          <div className={styles.uploadHint}>
            Formats acceptes : CSV, OFX, QFX, XML
          </div>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_EXTENSIONS}
            style={{ display: 'none' }}
            onChange={(e) => handleFileSelect(e.target.files)}
          />
        </div>
      )}

      {/* Upload result */}
      {uploadResult && (
        <div className={styles.resultCard}>
          <div className={cn(styles.resultHeader, styles.resultSuccess)}>
            <CheckCircle size={18} />
            Import reussi — {uploadResult.bankName}
          </div>
          <div className={styles.resultStats}>
            <span className={styles.resultStat}>
              <strong>{uploadResult.rowsImported}</strong> lignes importees
            </span>
            <span className={styles.resultStat}>
              <strong>{uploadResult.rowsSkipped}</strong> ignorees
            </span>
            <span className={styles.resultStat}>
              <strong>{uploadResult.rowsTotal}</strong> total
            </span>
            <span className={styles.resultStat}>
              Periode : <strong>{formatPeriod(uploadResult.dateRange)}</strong>
            </span>
          </div>
          {uploadResult.warnings.length > 0 && (
            <div className={styles.resultWarnings}>
              {uploadResult.warnings.map((w, i) => (
                <span key={i} className={styles.resultWarning}>
                  {w}
                </span>
              ))}
            </div>
          )}
          <button
            type="button"
            className={styles.dismissBtn}
            onClick={() => setUploadResult(null)}
          >
            Fermer
          </button>
        </div>
      )}

      {/* Upload error */}
      {uploadError && (
        <div className={styles.resultCard}>
          <div className={cn(styles.resultHeader, styles.resultError)}>
            <XCircle size={18} />
            {uploadError}
          </div>
          <button
            type="button"
            className={styles.dismissBtn}
            onClick={() => setUploadError(null)}
          >
            Fermer
          </button>
        </div>
      )}

      {/* Import history */}
      <div className={styles.tableContainer}>
        <div className={styles.tableToolbar}>
          <span className={styles.badge}>
            <FileText size={10} style={{ display: 'inline', verticalAlign: 'middle', marginRight: '0.25rem' }} />
            Historique
          </span>
          <span className={styles.tableTitle}>Imports precedents</span>
        </div>

        {isLoadingHistory ? (
          <div className={styles.loadingState}>
            <Loader2 className={styles.spinner} />
            Chargement...
          </div>
        ) : imports.length === 0 ? (
          <div className={styles.emptyRow}>Aucun import pour le moment</div>
        ) : (
          <table className={styles.historyTable}>
            <thead>
              <tr>
                <th>Date</th>
                <th>Banque</th>
                <th>Type</th>
                <th>Statut</th>
                <th>Importees</th>
                <th>Periode</th>
              </tr>
            </thead>
            <tbody>
              {imports.map((imp) => (
                <tr key={imp.id}>
                  <td>{formatDate(imp.createdAt)}</td>
                  <td>{imp.bankName}</td>
                  <td>{imp.fileType?.toUpperCase() ?? '—'}</td>
                  <td>
                    <span
                      className={cn(
                        styles.statusBadge,
                        statusBadgeClass(imp.status),
                      )}
                    >
                      {imp.status === 'imported' && <CheckCircle size={10} />}
                      {imp.status === 'failed' && <XCircle size={10} />}
                      {imp.status}
                    </span>
                  </td>
                  <td>{imp.rowsImported ?? '—'}</td>
                  <td>{formatPeriod(imp.dateRange)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
