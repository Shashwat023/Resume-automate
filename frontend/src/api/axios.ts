import axios, { type AxiosInstance, type AxiosError, type InternalAxiosRequestConfig } from 'axios';
import { env } from '../config/env';
import { CONSTANTS } from '../config/constants';

const api: AxiosInstance = axios.create({
  baseURL: env.VITE_API_BASE_URL,          // e.g. http://localhost:8000
  timeout: CONSTANTS.TIMEOUTS.API_REQUEST,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor – attach auth token when present
api.interceptors.request.use(
  (config: InternalAxiosRequestConfig) => {
    const token = localStorage.getItem(CONSTANTS.LOCAL_STORAGE_KEYS.AUTH_TOKEN);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error: AxiosError) => Promise.reject(error),
);

/**
 * An Error that still carries the HTTP status it came from.
 *
 * The interceptor below deliberately flattens Axios' error object down to a
 * plain Error so callers get a clean `.message` to show — but that also threw
 * the status code away, leaving no way for anything downstream to tell "404,
 * this resource simply doesn't exist yet" apart from "the network flaked".
 * react-query needs exactly that distinction to avoid retrying a 404
 * (FLAGGED.md #34.3), so the status is preserved here.
 */
interface ApiError extends Error {
  status?: number;
}

export function isNotFound(error: unknown): boolean {
  return (error as ApiError | null)?.status === 404;
}

// Response interceptor – unwrap data, handle 401
api.interceptors.response.use(
  (response) => response.data,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      localStorage.removeItem(CONSTANTS.LOCAL_STORAGE_KEYS.AUTH_TOKEN);
    }
    const errorMessage =
      (error.response?.data as Record<string, string>)?.detail ||
      (error.response?.data as Record<string, string>)?.message ||
      error.message ||
      'An unexpected error occurred';
    const apiError: ApiError = new Error(errorMessage);
    apiError.status = error.response?.status;
    return Promise.reject(apiError);
  },
);

export default api;
