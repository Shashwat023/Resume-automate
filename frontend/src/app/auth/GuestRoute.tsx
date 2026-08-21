import { Navigate, Outlet } from 'react-router';
import { useUserStore } from '../../store/userStore';
import { ROUTES } from '../../config/routes';

export const GuestRoute = () => {
  const { isAuthenticated, isLoading } = useUserStore();

  if (isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center bg-background">
        <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-primary"></div>
      </div>
    );
  }

  if (isAuthenticated) {
    return <Navigate to={ROUTES.DASHBOARD} replace />;
  }

  return <Outlet />;
};
