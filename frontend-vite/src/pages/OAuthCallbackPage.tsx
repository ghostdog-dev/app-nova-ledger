import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Spinner } from '@/components/ui/spinner';
import { Alert } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { completeOAuth } from '@/hooks/use-connections';
import { useNavigate, useSearchParams } from 'react-router-dom';


/**
 * F53 — OAuth callback page with client-side state validation.
 *
 * Before sending the OAuth code to the backend, we compare the `state`
 * parameter from the URL with the one we stored in sessionStorage when
 * the OAuth flow was initiated. This prevents CSRF attacks on the OAuth flow.
 *
 * F65 — Redirect URL validated to prevent open redirect.
 * F66 — OAuth error parameter sanitized via whitelist.
 */

/** F66 — Known OAuth error codes mapped to safe display messages. */
const KNOWN_OAUTH_ERRORS: Record<string, string> = {
  'access_denied': 'Authorization was denied by the user.',
  'invalid_request': 'The authorization request was invalid.',
  'unauthorized_client': 'The client is not authorized.',
  'unsupported_response_type': 'Unsupported response type.',
  'invalid_scope': 'Invalid permissions requested.',
  'server_error': 'The provider encountered an error.',
  'temporarily_unavailable': 'The provider is temporarily unavailable.',
};

/** F65 — Validate that a redirect URL is same-origin to prevent open redirect. */
function isSafeRedirect(url: string): boolean {
  try {
    const parsed = new URL(url, window.location.origin);
    return parsed.origin === window.location.origin;
  } catch {
    return false;
  }
}
export default function OAuthCallbackPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { t } = useTranslation();

  const [error, setError] = useState<string | null>(null);
  const [isProcessing, setIsProcessing] = useState(true);

  useEffect(() => {
    async function handleCallback() {
      try {
        const code = searchParams.get('code');
        const stateFromUrl = searchParams.get('state');
        const errorParam = searchParams.get('error');

        // F66 — OAuth provider returned an error: use whitelist instead of reflecting raw param
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

        // F53 — Validate state parameter against what we stored before redirect
        const storedState = sessionStorage.getItem('oauth_state');
        const storedProvider = sessionStorage.getItem('oauth_provider');

        if (!storedState) {
          setError('OAuth state not found. The authorization flow may have expired. Please try again.');
          setIsProcessing(false);
          return;
        }

        if (stateFromUrl !== storedState) {
          setError('OAuth state mismatch. This may indicate a CSRF attack. Please try again.');
          setIsProcessing(false);
          // Clean up stored state
          sessionStorage.removeItem('oauth_state');
          sessionStorage.removeItem('oauth_provider');
          return;
        }

        // State validated — clean up storage
        sessionStorage.removeItem('oauth_state');
        sessionStorage.removeItem('oauth_provider');

        // Complete the OAuth flow via the backend
        const redirectUri = `${window.location.origin}/connections/oauth/callback`;
        await completeOAuth({
          providerName: storedProvider ?? '',
          code,
          state: stateFromUrl,
          redirectUri,
        });

        // F65 — Validate redirect target before navigation to prevent open redirect
        const redirectTarget = sessionStorage.getItem('oauth_redirect') ?? '/connections';
        sessionStorage.removeItem('oauth_redirect');
        navigate(isSafeRedirect(redirectTarget) ? redirectTarget : '/connections');
      } catch (err) {
        const message = (err as { message?: string })?.message ?? 'Failed to complete OAuth connection.';
        setError(message);
      } finally {
        setIsProcessing(false);
      }
    }

    handleCallback();
  }, [searchParams, navigate, t]);

  if (isProcessing) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 'var(--space-md)', padding: 'var(--space-5xl) 0' }}>
        <Spinner size="lg" />
        <p style={{ fontSize: '0.875rem', color: 'var(--color-text-muted)' }}>Completing connection...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ maxWidth: '28rem', margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 'var(--space-md)', padding: 'var(--space-2xl) 0' }}>
        <Alert variant="error">{error}</Alert>
        <Button
          fullWidth
          onClick={() => navigate('/connections')}
        >
          Back to Connections
        </Button>
      </div>
    );
  }

  return null;
}
