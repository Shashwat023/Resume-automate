export const CONSTANTS = {
  APP_NAME: 'Auto Apply Platform',
  LOCAL_STORAGE_KEYS: {
    THEME: 'auto-apply-theme',
    AUTH_TOKEN: 'auto-apply-auth-token',
    USER_PREFERENCES: 'auto-apply-user-prefs',
  },
  PAGINATION: {
    DEFAULT_PAGE: 1,
    DEFAULT_LIMIT: 10,
  },
  TIMEOUTS: {
    API_REQUEST: 30000, // 30 seconds
  },
  SUPPORTED_RESUME_FORMATS: ['.pdf', '.doc', '.docx'],
  MAX_RESUME_SIZE_MB: 5,
} as const;
