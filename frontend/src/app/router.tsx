import { createBrowserRouter } from 'react-router';
import { lazy, Suspense } from 'react';
import { DashboardLayout } from '../layouts/DashboardLayout';
import { ProtectedRoute } from './auth/ProtectedRoute';
import { PageLoader } from '../components/ui/PageLoader';
import { ROUTES } from '../config/routes';
import { NotFoundPage } from '../pages/NotFoundPage';

const DashboardPage = lazy(() => import('../pages/DashboardPage').then(module => ({ default: module.DashboardPage })));
const SearchPage = lazy(() => import('../pages/SearchPage').then(module => ({ default: module.SearchPage })));
const UploadResumePage = lazy(() => import('../pages/UploadResumePage').then(module => ({ default: module.UploadResumePage })));
const ProfilePage = lazy(() => import('../pages/ProfilePage').then(module => ({ default: module.ProfilePage })));
const SettingsPage = lazy(() => import('../pages/SettingsPage').then(module => ({ default: module.SettingsPage })));
const QueuePage = lazy(() => import('../pages/QueuePage').then(module => ({ default: module.QueuePage })));
const AdminPage = lazy(() => import('../pages/AdminPage').then(module => ({ default: module.AdminPage })));

export const router = createBrowserRouter([
  {
    path: '/',
    element: <ProtectedRoute />,
    children: [
      {
        path: '/',
        element: <DashboardLayout />,
        children: [
          {
            index: true,
            element: (
              <Suspense fallback={<PageLoader />}>
                <DashboardPage />
              </Suspense>
            ),
          },
          {
            path: ROUTES.SEARCH,
            element: (
              <Suspense fallback={<PageLoader />}>
                <SearchPage />
              </Suspense>
            ),
          },
          {
            path: ROUTES.UPLOAD_RESUME,
            element: (
              <Suspense fallback={<PageLoader />}>
                <UploadResumePage />
              </Suspense>
            ),
          },
          {
            path: ROUTES.PROFILE,
            element: (
              <Suspense fallback={<PageLoader />}>
                <ProfilePage />
              </Suspense>
            ),
          },
          {
            path: ROUTES.QUEUE,
            element: (
              <Suspense fallback={<PageLoader />}>
                <QueuePage />
              </Suspense>
            ),
          },
          {
            path: ROUTES.ADMIN,
            element: (
              <Suspense fallback={<PageLoader />}>
                <AdminPage />
              </Suspense>
            ),
          },
          {
            path: '*',
            element: <NotFoundPage />,
          },
        ],
      },
    ],
  },
  {
    path: ROUTES.LOGIN,
    element: <div className="flex h-screen items-center justify-center">Login Page Placeholder</div>,
  },
]);