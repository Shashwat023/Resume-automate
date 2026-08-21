import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import type { Resume } from '../types';

interface ResumeState {
  activeResume: Resume | null;
  setActiveResume: (resume: Resume | null) => void;
  clearResume: () => void;
}

export const useResumeStore = create<ResumeState>()(
  persist(
    (set) => ({
      activeResume: null,
      setActiveResume: (resume) => set({ activeResume: resume }),
      clearResume: () => set({ activeResume: null }),
    }),
    {
      name: 'auto-apply-resume-state',
    }
  )
);
