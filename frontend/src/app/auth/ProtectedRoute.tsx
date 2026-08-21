import { Navigate, Outlet, useLocation } from 'react-router';
import { useUserStore } from '../../store/userStore';
import { ROUTES } from '../../config/routes';

export const ProtectedRoute = () => {
  const { isAuthenticated, isLoading } = useUserStore();
  const location = useLocation();

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary"></div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to={ROUTES.LOGIN} state={{ from: location }} replace />;
  }

  return <Outlet />;
};
