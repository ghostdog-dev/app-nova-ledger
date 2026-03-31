import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { Spinner } from '@/components/ui/spinner';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { apiClient, storeAccessToken } from '@/lib/api-client';
import { completeOAuth } from '@/hooks/use-connections';
import { useAuthStore } from '@/stores/auth-store';
import { useCompanyStore } from '@/stores/company-store';
import type { AuthResponse } from '@/types';

const KNOWN_OAUTH_ERRORS: Record<string, string> = {
  'access_denied': 'Authorization was denied by the user.',
  'invalid_request': 'The authorization request was invalid.',
  'unauthorized_client': 'The client is not authorized.',
  'unsupported_response_type': 'Unsupported response type.',
  'invalid_scope': 'Invalid permissions requested.',
  'server_error': 'The provider encountered an error.',
  'temporarily_unavailable': 'The provider is temporarily unavailable.',
};

export default function SocialAuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const setAuth = useAuthStore((s) => s.setAuth);

  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    async function handleCallback() {
      try {
        const code = searchParams.get('code');
        const stateFromUrl = searchParams.get('state');
        const errorParam = searchParams.get('error');

        if (errorParam) {
          setError(KNOWN_OAUTH_ERRORS[errorParam] ?? 'An unexpected error occurred during authentication.');
          setIsProcessing(false);
          return;
        }

        if (!code || !stateFromUrl) {
          setError('Missing authorization code or state parameter.');
          setIsProcessing(false);
          return;
        }

        // Determine which flow: social login or connection OAuth
        const socialState = sessionStorage.getItem('social_oauth_state');
        const socialProvider = sessionStorage.getItem('social_oauth_provider');
        const connState = sessionStorage.getItem('oauth_state');
        const connProvider = sessionStorage.getItem('oauth_provider');

        const redirectUri = `${window.location.origin}/auth/callback`;

        if (socialState && stateFromUrl === socialState) {
          // --- Social login flow ---
          sessionStorage.removeItem('social_oauth_state');
          sessionStorage.removeItem('social_oauth_provider');

          const response = await apiClient.post<AuthResponse>('/accounts/social-login/', {
            provider: socialProvider,
            code,
            redirectUri,
          });

          storeAccessToken(response.tokens.accessToken);
          setAuth(response.user, response.tokens.accessToken);
          // Load companies before navigating so dashboard has an active company
          await useCompanyStore.getState().fetchCompanies();
          navigate('/dashboard');

        } else if (connState && stateFromUrl === connState) {
          // --- Connection OAuth flow (add provider like Outlook) ---
          sessionStorage.removeItem('oauth_state');
          sessionStorage.removeItem('oauth_provider');

          await completeOAuth({
            providerName: connProvider ?? '',
            code,
            state: stateFromUrl,
            redirectUri,
          });

          navigate('/connections');

        } else {
          setError('OAuth state mismatch. Please try again.');
          sessionStorage.removeItem('social_oauth_state');
          sessionStorage.removeItem('social_oauth_provider');
          sessionStorage.removeItem('oauth_state');
          sessionStorage.removeItem('oauth_provider');
        }
      } catch (err) {
        const message = (err as { message?: string })?.message ?? 'Failed to complete authentication.';
        setError(message);
      } finally {
        setIsProcessing(false);
      }
    }

    handleCallback();
  }, [searchParams, navigate, setAuth]);

  if (isProcessing) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-md)', padding: 'var(--space-5xl) 0' }}>
        <Spinner size="lg" />
        <p style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>Completing sign in...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: '28rem', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-md)', padding: 'var(--space-2xl) 0' }}>
        <Alert variant="error">{error}</Alert>
        <Button fullWidth onClick={() => navigate('/login')}>
          Back to Login
        </Button>
      </div>
    );
  }

  return null;
}
