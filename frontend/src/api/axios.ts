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
    return Promise.reject(new Error(errorMessage));
  },
);

export default api;
