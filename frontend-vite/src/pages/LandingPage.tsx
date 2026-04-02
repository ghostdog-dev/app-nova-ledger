import { LandingPage } from '@/components/landing/landing-page';

/**
 * Root page — renders landing page.
 * Auth redirect is handled by the router (PrivateRoute/AuthRoute wrapper).
 */
export default function RootPage() {
  return <LandingPage />;
}
