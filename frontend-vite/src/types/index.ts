// ============================================================
// Shared TypeScript types for the Nova Ledger frontend
// Aligned with backend serializers (camelCase via djangorestframework-camel-case)
// ============================================================

// --- Auth ---

export interface UserProfile {
  plan: 'free' | 'plan1' | 'plan2';
  language: string;
  totpEnabled: boolean;
  emailNotifications: boolean;
  avatarUrl: string;
}

export interface User {
  id: number;
  email: string;
  firstName: string;
  lastName: string;
  avatarUrl: string;
  plan: 'free' | 'plan1' | 'plan2';
  emailVerified: boolean;
  createdAt: string;
  profile?: UserProfile;
}

export interface AuthTokens {
  accessToken: string;
  // refreshToken is stored as httpOnly cookie by the backend, not in JSON body
}

export interface LoginRequest {
  email: string;
  password: string;
}

export interface RegisterRequest {
  email: string;
  password: string;
  firstName: string;
  lastName: string;
}

export interface AuthResponse {
  user: User;
  tokens: AuthTokens;
}

// --- Company ---

export type PlanType = 'free' | 'plan1' | 'plan2';
export type MemberRole = 'owner' | 'admin' | 'member';

export interface SubscriptionStatus {
  status: 'active' | 'past_due' | 'canceled' | 'paused' | 'trialing' | 'none';
  plan: PlanType;
  currentPeriodEnd: string | null;
  cancelAtPeriodEnd: boolean;
}

export interface Company {
  publicId: string;
  name: string;
  siret?: string;
  sector?: string;
  owner: User;
  plan: PlanType;
  isActive: boolean;
  logoUrl?: string;
  brandColor?: string;
  createdAt: string;
  updatedAt: string;
  memberCount: number;
}

export interface CompanyPlan {
  plan: PlanType;
  planDisplay: string;
  limits: Record<string, number | null>;
}

export interface CompanyUsage {
  executionsThisMonth: number;
  connections: number;
  members: number;
  limits: Record<string, number | null>;
}

export interface CompanyMember {
  id: number;
  user: User;
  userId: number;
  role: MemberRole;
  isActive: boolean;
  createdAt: string;
}

export interface InviteMemberPayload {
  email: string;
  role: MemberRole;
}

export interface QuotaExceededDetail {
  quota_exceeded: true;
  resource: string;
  current: number;
  max: number;
  detail: string;
}

// --- Service Connections ---

export type ConnectionStatus = 'active' | 'expired' | 'error' | 'pending';
export type ServiceType = 'invoicing' | 'payment' | 'email' | 'banking';
export type AuthType = 'oauth' | 'api_key';

export interface ServiceConnection {
  publicId: string;
  company: string;
  companyName: string;
  serviceType: ServiceType;
  providerName: string;
  status: ConnectionStatus;
  authType: AuthType;
  lastSync?: string | null;
  errorMessage?: string;
  tokenExpiresAt?: string | null;
  createdAt: string;
  updatedAt: string;
}

// --- Executions ---

export type ExecutionStatus = 'pending' | 'running' | 'completed' | 'failed';

export interface ExecutionSummary {
  invoicesProcessed: number;
  correlationsFound: number;
  anomaliesDetected: number;
  reconciliationRate: number;
}

export interface Execution {
  publicId: string;
  company: string;
  companyName: string;
  user: string;
  userEmail: string;
  status: ExecutionStatus;
  dateFrom: string;
  dateTo: string;
  dateStart?: string | null;
  dateEnd?: string | null;
  granularity: string;
  includedConnections: number[];
  parameters?: Record<string, unknown>;
  summary?: ExecutionSummary | null;
  errorMessage?: string;
  durationSeconds?: number | null;
  createdAt: string;
  updatedAt: string;
}

export interface CreateExecutionPayload {
  dateFrom: string;
  dateTo: string;
  includedConnections: string[];
  parameters?: Record<string, unknown>;
}

// --- Execution Progress (WebSocket) ---

export type ExecutionStepId =
  | 'triage'
  | 'extraction'
  | 'merge'
  | 'computation'
  | 'bank_correlation'
  | 'provider_correlation'
  | 'report';

export interface ExecutionStep {
  id: ExecutionStepId;
  label: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  message?: string;
  startedAt?: string;
  completedAt?: string;
}

export interface ExecutionProgress {
  executionId: string;
  currentStepIndex: number;
  totalSteps: number;
  percentage: number;
  steps: ExecutionStep[];
  status: ExecutionStatus;
  error?: string;
}

// WebSocket message shapes
export type ProgressMessage =
  | { type: 'progress'; step: ExecutionStepId; stepIndex: number; totalSteps: number; percentage: number; message: string }
  | { type: 'completed'; summary: ExecutionSummary }
  | { type: 'failed'; error: string };

// --- Correlations ---

export type CorrelationStatus =
  | 'reconciled'
  | 'reconciled_with_alert'
  | 'unpaid'
  | 'orphan_payment'
  | 'uncertain';

export interface InvoiceMini {
  publicId: string;
  numero: string;
  dateEmission: string;
  dateEcheance: string | null;
  montantHt: string;  // Decimal comes as string from DRF
  montantTtc: string;
  devise: string;
  statut: string;
  client: string;
  fournisseur: string;
  source: string;
}

export interface PaymentMini {
  publicId: string;
  date: string;
  montant: string;  // Decimal comes as string from DRF
  devise: string;
  methode: string;
  statut: string;
  reference: string;
  emetteur: string;
  source: string;
}

export interface Correlation {
  publicId: string;
  invoice: InvoiceMini | null;
  payment: PaymentMini | null;
  scoreConfiance: number;
  statut: CorrelationStatus;
  matchCriteria: string | null;
  isManual: boolean;
  notes: string | null;
  anomalies?: Anomaly[];
  createdAt: string;
}

export interface Anomaly {
  publicId: string;
  type: string;
  description: string;
  severity: string;
  correlationId: number | null;
  invoice: InvoiceMini | null;
  payment: PaymentMini | null;
  amountImpact: string | null;
  isResolved: boolean;
  resolutionNotes: string | null;
  createdAt: string;
}

export interface CorrelationUpdatePayload {
  statut?: CorrelationStatus;
  notes?: string;
  isManual?: boolean;
}

export type ExportFormat = 'csv' | 'excel' | 'pdf' | 'json';

export interface ExportFile {
  id: number;
  publicId: string;
  format: ExportFormat;
  status: 'pending' | 'generating' | 'ready' | 'error' | 'expired';
  fileUrl: string;
  fileSize: number;
  fileSizeMb: number;
  originalFilename: string;
  errorMessage: string;
  urlExpiresAt: string | null;
  celeryTaskId: string;
  createdAt: string;
  updatedAt: string;
}

// --- Chat ---

export interface ChatMessage {
  id: number | string;
  role: 'user' | 'assistant';
  content: string;
  createdAt: string;
}

export interface ChatSession {
  id: number;
  publicId: string;
  company: number;
  execution: number | null;
  language: string;
  title: string;
  isActive: boolean;
  totalTokensUsed: number;
  messageCount: number;
  messages: ChatMessage[];
  createdAt: string;
  updatedAt: string;
}

export interface CreateChatSessionPayload {
  executionId?: number | null;
  language?: string;
  title?: string;
}

export interface SendChatMessagePayload {
  content: string;
}

// --- API ---

export interface ApiError {
  status: number;
  message: string;
  detail?: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

// --- UI ---

export type AlertVariant = 'info' | 'success' | 'warning' | 'error';
export type BadgeVariant = 'default' | 'success' | 'warning' | 'error' | 'info';
export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';
export type SortDirection = 'asc' | 'desc';
