import { create } from 'zustand';

interface User {
  id: string;
  email: string;
  name: string;
  role?: string;
  avatarUrl?: string;
}

interface UserState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  setUser: (user: User | null) => void;
  setLoading: (loading: boolean) => void;
  logout: () => void;
}

export const useUserStore = create<UserState>((set) => ({
  user: {
    id: '1',
    name: 'Enterprise Admin',
    email: 'admin@autoapply.ai'
  },
  isAuthenticated: true,
  isLoading: false,
  setUser: (user) => set({ user, isAuthenticated: !!user }),
  setLoading: (isLoading) => set({ isLoading }),
  logout: () => set({ user: null, isAuthenticated: false }),
}));
