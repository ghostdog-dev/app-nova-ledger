import type { ApiError, QuotaExceededDetail } from '@/types';
import { generateFingerprint } from '@/lib/fingerprint';

/**
 * API base URL — uses relative path so requests go through the dev proxy
 * (same-origin), ensuring httpOnly cookies (SameSite=Lax) are always sent.
 * Direct cross-origin requests (e.g. localhost:5173 → localhost:8000) would
 * NOT attach SameSite=Lax cookies on POST, breaking token refresh.
 */
const API_BASE_URL = import.meta.env.VITE_API_URL ?? '/api/v1';

// ---------------------------------------------------------------------------
// Device fingerprint — generated once and cached for the page lifetime.
// Sent as X-Device-Fingerprint so the backend can build a composite
// rate-limit key (fingerprint + IP) resilient to IP rotation.
// ---------------------------------------------------------------------------
let _fingerprint: string | null = null;

async function getFingerprint(): Promise<string> {
  if (!_fingerprint) {
    try {
      _fingerprint = await generateFingerprint();
    } catch {
      // Fallback: if crypto.subtle is unavailable (e.g. non-secure context),
      // the backend will fall back to IP-only rate limiting.
      _fingerprint = '';
    }
  }
  return _fingerprint;
}

type RequestMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

interface RequestOptions {
  method?: RequestMethod;
  body?: unknown;
  headers?: Record<string, string>;
  signal?: AbortSignal;
}

/**
 * [F05] Access token stored in-memory only (not localStorage).
 * This prevents XSS exfiltration. On page refresh the token is lost,
 * but the httpOnly refresh cookie can obtain a new one transparently.
 */
let _accessToken: string | null = null;

export function getStoredAccessToken(): string | null {
  return _accessToken;
}

export function storeAccessToken(accessToken: string): void {
  _accessToken = accessToken;
}

export function clearStoredTokens(): void {
  _accessToken = null;
}

// Keep backward compat for callers that pass both tokens
export function storeTokens(accessToken: string, _refreshToken?: string): void {
  storeAccessToken(accessToken);
  // Refresh token is now stored as httpOnly cookie by the backend — not in localStorage
}

/**
 * [F05] Attempt to restore the access token from the httpOnly refresh cookie.
 * Call this on app mount / page load so that in-memory token is replenished
 * after a browser refresh without requiring the user to log in again.
 * Returns true if a valid access token was obtained.
 */
export async function initializeAuth(): Promise<boolean> {
  if (_accessToken) return true;
  const token = await refreshAccessToken();
  return token !== null;
}

/**
 * Circuit breaker: prevents infinite refresh loops.
 * If refresh fails, block further attempts for a cooldown period.
 */
let _refreshFailed = false;
let _refreshPromise: Promise<string | null> | null = null;

/**
 * Attempt to refresh the access token.
 * The refresh token is sent automatically as an httpOnly cookie by the browser.
 * Deduplicates concurrent calls and blocks retries after failure.
 */
async function refreshAccessToken(): Promise<string | null> {
  // Circuit breaker: don't retry if we already know refresh is broken
  if (_refreshFailed) return null;

  // Deduplicate: if a refresh is already in-flight, wait for it
  if (_refreshPromise) return _refreshPromise;

  _refreshPromise = (async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/accounts/token/refresh/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include', // send httpOnly cookie
        body: JSON.stringify({}),
      });

      if (!response.ok) {
        clearStoredTokens();
        _refreshFailed = true;
        return null;
      }

      const data = await response.json();
      const newAccessToken: string = data.access;
      storeAccessToken(newAccessToken);
      return newAccessToken;
    } catch {
      clearStoredTokens();
      _refreshFailed = true;
      return null;
    } finally {
      _refreshPromise = null;
    }
  })();

  return _refreshPromise;
}

/** Reset circuit breaker (call on successful login). */
export function resetRefreshState(): void {
  _refreshFailed = false;
  _refreshPromise = null;
}

/**
 * Core fetch wrapper with:
 * - Automatic JWT Authorization header
 * - Automatic token refresh on 401
 * - credentials: 'include' for httpOnly cookie support
 * - Standardized error handling
 */
async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, headers = {}, signal } = options;

  const accessToken = getStoredAccessToken();
  const fingerprint = await getFingerprint();
  const requestHeaders: Record<string, string> = {
    'Content-Type': 'application/json',
    ...headers,
  };

  if (fingerprint) {
    requestHeaders['X-Device-Fingerprint'] = fingerprint;
  }

  if (accessToken) {
    requestHeaders['Authorization'] = `Bearer ${accessToken}`;
  }

  const url = endpoint.startsWith('http') ? endpoint : `${API_BASE_URL}${endpoint}`;

  const fetchOptions: RequestInit = {
    method,
    headers: requestHeaders,
    credentials: 'include', // always send cookies (refresh token)
    signal,
  };

  if (body !== undefined) {
    fetchOptions.body = JSON.stringify(body);
  }

  let response = await fetch(url, fetchOptions);

  // Attempt token refresh on 401 — but only if we had a token (i.e. user
  // was logged in). Unauthenticated endpoints like /login/ return 401 for
  // bad credentials — those should NOT trigger a refresh attempt.
  if (response.status === 401 && accessToken) {
    const newToken = await refreshAccessToken();
    if (newToken) {
      requestHeaders['Authorization'] = `Bearer ${newToken}`;
      response = await fetch(url, { ...fetchOptions, headers: requestHeaders });
    } else {
      // Don't redirect here — let the auth store's onRehydrateStorage handle it.
      // A hard redirect to /login causes an infinite loop with the middleware
      // when the refresh cookie exists but is invalid.
      const error: ApiError = { status: 401, message: 'Session expired' };
      throw error;
    }
  }

  // Handle rate limiting / quota exceeded
  if (response.status === 429) {
    let detail: Partial<QuotaExceededDetail> | undefined;
    try {
      detail = await response.json();
    } catch {
      // Ignore JSON parse errors
    }

    // If it's a quota error from QuotaMiddleware, emit a custom event
    if (detail?.quota_exceeded && typeof window !== 'undefined') {
      window.dispatchEvent(new CustomEvent('quota-exceeded', { detail }));
    }

    const error: ApiError = {
      status: 429,
      message: detail?.detail ?? 'Too many requests. Please wait.',
    };
    throw error;
  }

  if (!response.ok) {
    let errorMessage = `HTTP error ${response.status}`;
    try {
      const errorData = await response.json();
      if (errorData.detail) {
        errorMessage = errorData.detail;
      } else if (errorData.message) {
        errorMessage = errorData.message;
      } else {
        // DRF field-level errors: {password: ["Too short"], email: ["Invalid"]}
        const fieldErrors = Object.entries(errorData)
          .map(([, msgs]) => (Array.isArray(msgs) ? msgs.join(' ') : String(msgs)))
          .join(' ');
        if (fieldErrors) errorMessage = fieldErrors;
      }
    } catch {
      // Ignore JSON parse errors
    }

    const error: ApiError = {
      status: response.status,
      message: errorMessage,
    };
    throw error;
  }

  // Handle empty responses (204 No Content)
  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

/**
 * [F06] Obtain a short-lived, single-use WebSocket ticket.
 * Use this instead of passing the JWT in WebSocket URL query strings.
 * The ticket is consumed on first use and expires after 30 seconds.
 */
export async function getWsTicket(): Promise<string | null> {
  try {
    const data = await request<{ ticket: string }>('/ws/ticket/', { method: 'POST' });
    return data.ticket;
  } catch {
    return null;
  }
}

/** HTTP client with typed methods */
export const apiClient = {
  get: <T>(endpoint: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(endpoint, { ...options, method: 'GET' }),

  post: <T>(endpoint: string, body?: unknown, options?: Omit<RequestOptions, 'method'>) =>
    request<T>(endpoint, { ...options, method: 'POST', body }),

  put: <T>(endpoint: string, body?: unknown, options?: Omit<RequestOptions, 'method'>) =>
    request<T>(endpoint, { ...options, method: 'PUT', body }),

  patch: <T>(endpoint: string, body?: unknown, options?: Omit<RequestOptions, 'method'>) =>
    request<T>(endpoint, { ...options, method: 'PATCH', body }),

  delete: <T>(endpoint: string, options?: Omit<RequestOptions, 'method' | 'body'>) =>
    request<T>(endpoint, { ...options, method: 'DELETE' }),
};
