import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Profile } from '../types';

interface ProfileState {
  profile: Profile | null;
  setProfile: (profile: Profile) => void;
  importProfile: (profileData: string) => boolean;
  exportProfile: () => string;
}

export const useProfileStore = create<ProfileState>()(
  persist(
    (set, get) => ({
      profile: null,
      setProfile: (profile) => set({ profile }),
      importProfile: (jsonString) => {
        try {
          const parsed = JSON.parse(jsonString);
          // In a real app we'd validate against zod schema here too
          set({ profile: parsed });
          return true;
        } catch (e) {
          return false;
        }
      },
      exportProfile: () => {
        const { profile } = get();
        return JSON.stringify(profile || {}, null, 2);
      }
    }),
    {
      name: 'auto-apply-profile-state',
    }
  )
);
