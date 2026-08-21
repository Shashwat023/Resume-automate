import { z } from 'zod';

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().url().default('http://localhost:8000'),
  VITE_APP_ENV: z.enum(['development', 'production', 'test']).default('development'),
  VITE_APP_NAME: z.string().default('Career-Ops'),
  // Profile ID persisted after first creation; stored in localStorage.
  // This lets the single-user MVP work without a full auth system.
  VITE_DEFAULT_PROFILE_ID: z.coerce.number().optional(),
});

const parseEnv = () => {
  try {
    return envSchema.parse({
      VITE_API_BASE_URL: import.meta.env.VITE_API_BASE_URL,
      VITE_APP_ENV: import.meta.env.VITE_APP_ENV,
      VITE_APP_NAME: import.meta.env.VITE_APP_NAME,
      VITE_DEFAULT_PROFILE_ID: import.meta.env.VITE_DEFAULT_PROFILE_ID,
    });
  } catch (error) {
    console.error('Invalid environment variables:', error);
    return {
      VITE_API_BASE_URL: 'http://localhost:8000',
      VITE_APP_ENV: 'development' as const,
      VITE_APP_NAME: 'Career-Ops',
      VITE_DEFAULT_PROFILE_ID: undefined,
    };
  }
};

export const env = parseEnv();
