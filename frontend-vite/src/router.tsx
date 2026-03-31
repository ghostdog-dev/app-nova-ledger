import { createBrowserRouter, Outlet } from 'react-router-dom';
import { lazy, Suspense } from 'react';
import { AuthGuard } from '@/guards/AuthGuard';
import { GuestGuard } from '@/guards/GuestGuard';
import { AppLayout } from '@/layouts/AppLayout';
import { AuthLayout } from '@/layouts/AuthLayout';
import { Spinner } from '@/components/ui/spinner';

// Lazy-loaded pages
const LandingPage = lazy(() => import('@/pages/LandingPage'));
const LoginPage = lazy(() => import('@/pages/LoginPage'));
const RegisterPage = lazy(() => import('@/pages/RegisterPage'));
const DashboardPage = lazy(() => import('@/pages/DashboardPage'));
const ConnectionsPage = lazy(() => import('@/pages/ConnectionsPage'));
const OAuthCallbackPage = lazy(() => import('@/pages/OAuthCallbackPage'));
const ExecutionsPage = lazy(() => import('@/pages/ExecutionsPage'));
const NewExecutionPage = lazy(() => import('@/pages/NewExecutionPage'));
const ExecutionDetailPage = lazy(() => import('@/pages/ExecutionDetailPage'));
const TransactionsPage = lazy(() => import('@/pages/TransactionsPage'));
const SourcesPage = lazy(() => import('@/pages/SourcesPage'));
const BankImportPage = lazy(() => import('@/pages/BankImportPage'));
const SettingsPage = lazy(() => import('@/pages/SettingsPage'));
const CompanySettingsPage = lazy(() => import('@/pages/CompanySettingsPage'));
const PlansPage = lazy(() => import('@/pages/PlansPage'));
const SocialAuthCallbackPage = lazy(() => import('@/pages/SocialAuthCallbackPage'));
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'));

function SuspenseWrapper() {
  return (
    <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}><Spinner /></div>}>
      <Outlet />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <SuspenseWrapper />,
    children: [
      // Public routes
      { path: '/', element: <LandingPage /> },
      { path: '/auth/callback', element: <SocialAuthCallbackPage /> },

      // Guest-only routes (redirect to /dashboard if already authenticated)
      {
        element: <GuestGuard />,
        children: [
          {
            element: <AuthLayout />,
            children: [
              { path: '/login', element: <LoginPage /> },
              { path: '/register', element: <RegisterPage /> },
            ],
          },
        ],
      },

      // Protected routes (redirect to /login if not authenticated)
      {
        element: <AuthGuard />,
        children: [
          {
            element: <AppLayout />,
            children: [
              { path: '/dashboard', element: <DashboardPage /> },
              { path: '/connections', element: <ConnectionsPage /> },
              { path: '/connections/oauth/callback', element: <OAuthCallbackPage /> },
              { path: '/executions', element: <ExecutionsPage /> },
              { path: '/executions/new', element: <NewExecutionPage /> },
              { path: '/executions/:id', element: <ExecutionDetailPage /> },
              { path: '/transactions', element: <TransactionsPage /> },
              { path: '/sources', element: <SourcesPage /> },
              { path: '/bank-import', element: <BankImportPage /> },
              { path: '/settings', element: <SettingsPage /> },
              { path: '/settings/company', element: <CompanySettingsPage /> },
              { path: '/settings/plans', element: <PlansPage /> },
            ],
          },
        ],
      },

      // 404
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);
