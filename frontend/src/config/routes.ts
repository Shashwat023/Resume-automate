export const ROUTES = {
  HOME: '/',
  DASHBOARD: '/',
  SEARCH: '/search',
  UPLOAD_RESUME: '/upload-resume',
  PROFILE: '/profile',
  QUEUE: '/queue',
  SETTINGS: '/settings',
  ADMIN: '/admin',
  LOGIN: '/login',
  REGISTER: '/register',
} as const;

export type RouteKey = keyof typeof ROUTES;
export type RoutePath = typeof ROUTES[RouteKey];