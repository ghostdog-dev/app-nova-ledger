import { useState, useCallback, useRef } from 'react';
import { apiClient } from '@/lib/api-client';
import type { ApiError } from '@/types';

interface UseApiState<T> {
  data: T | null;
  isLoading: boolean;
  error: ApiError | null;
}

interface UseApiOptions {
  onSuccess?: (data: unknown) => void;
  onError?: (error: ApiError) => void;
}

/**
 * Generic hook for API calls with loading and error state management.
 */
export function useApi<T>(options: UseApiOptions = {}) {
  const [state, setState] = useState<UseApiState<T>>({
    data: null,
    isLoading: false,
    error: null,
  });

  const abortControllerRef = useRef<AbortController | null>(null);

  const execute = useCallback(
    async (
      method: 'get' | 'post' | 'put' | 'patch' | 'delete',
      endpoint: string,
      body?: unknown
    ): Promise<T | null> => {
      // Abort previous in-flight request
      abortControllerRef.current?.abort();
      abortControllerRef.current = new AbortController();

      setState((prev) => ({ ...prev, isLoading: true, error: null }));

      try {
        let data: T;
        const signal = abortControllerRef.current.signal;

        if (method === 'get' || method === 'delete') {
          data = await apiClient[method]<T>(endpoint, { signal });
        } else {
          data = await apiClient[method]<T>(endpoint, body, { signal });
        }

        setState({ data, isLoading: false, error: null });
        options.onSuccess?.(data);
        return data;
      } catch (err) {
        if ((err as Error).name === 'AbortError') return null;

        const apiError = err as ApiError;
        setState((prev) => ({ ...prev, isLoading: false, error: apiError }));
        options.onError?.(apiError);
        return null;
      }
    },
    [options]
  );

  const reset = useCallback(() => {
    abortControllerRef.current?.abort();
    setState({ data: null, isLoading: false, error: null });
  }, []);

  return {
    ...state,
    execute,
    reset,
  };
}
