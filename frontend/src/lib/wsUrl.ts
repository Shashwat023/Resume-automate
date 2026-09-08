import { env } from '../config/env';

/** Converts the configured http(s) API base URL into the matching ws(s) origin. */
export function wsUrl(path: string): string {
  const httpBase = env.VITE_API_BASE_URL.replace(/\/$/, '');
  const wsBase = httpBase.replace(/^http/, 'ws');
  return `${wsBase}${path}`;
}
