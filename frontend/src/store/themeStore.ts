import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { CONSTANTS } from '../config/constants';

interface ThemeState {
  theme: 'light' | 'dark' | 'system';
  setTheme: (theme: 'light' | 'dark' | 'system') => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set) => ({
      theme: 'system',
      setTheme: (theme) => set({ theme }),
    }),
    {
      name: CONSTANTS.LOCAL_STORAGE_KEYS.THEME,
    }
  )
);
