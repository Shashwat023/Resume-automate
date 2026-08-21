import { Link } from 'react-router';
import { ROUTES } from '../config/routes';

export const NotFoundPage = () => {
  return (
    <div className="flex h-[80vh] flex-col items-center justify-center space-y-4 text-center">
      <h1 className="text-9xl font-extrabold text-gray-200 dark:text-gray-800">404</h1>
      <h2 className="text-3xl font-bold tracking-tight text-gray-900 dark:text-gray-100">Page not found</h2>
      <p className="max-w-md text-gray-500 dark:text-gray-400">
        Sorry, we couldn't find the page you're looking for. Perhaps you've mistyped the URL or the page has been moved.
      </p>
      <Link
        to={ROUTES.DASHBOARD}
        className="inline-flex h-10 items-center justify-center rounded-md bg-indigo-600 px-8 text-sm font-medium text-white transition-colors hover:bg-indigo-700 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-indigo-700"
      >
        Back to Dashboard
      </Link>
    </div>
  );
};
