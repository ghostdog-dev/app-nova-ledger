/**
 * Social OAuth helpers — fetches the authorization URL from the backend
 * and redirects the browser to the provider's consent screen.
 *
 * Client IDs stay server-side — never exposed in frontend code.
 * State is stored in sessionStorage so the callback page can validate it.
 */

import { apiClient } from './api-client';

type SocialProvider = 'google' | 'microsoft';

export async function startSocialLogin(provider: SocialProvider): Promise<void> {
  const redirectUri = `${window.location.origin}/auth/callback`;

  // Ask the backend to build the OAuth URL (keeps client_id server-side)
  const { authorizationUrl, state } = await apiClient.post<{ authorizationUrl: string; state: string }>(
    '/accounts/social-auth-url/',
    { provider, redirectUri },
  );

  // Store state + provider in sessionStorage for CSRF validation on callback
  sessionStorage.setItem('social_oauth_state', state);
  sessionStorage.setItem('social_oauth_provider', provider);

  window.location.href = authorizationUrl;
}
