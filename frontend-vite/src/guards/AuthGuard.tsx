import { Navigate, Outlet, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/stores/auth-store';
import { Spinner } from '@/components/ui/spinner';

export function AuthGuard() {
  const { isAuthenticated, isHydrating } = useAuthStore();
  const location = useLocation();

  // Wait for auth state to be restored from localStorage + token refresh
  if (isHydrating) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
        <Spinner />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  }

  return <Outlet />;
}
