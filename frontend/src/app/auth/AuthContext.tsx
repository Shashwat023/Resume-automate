import { createContext, useContext, type ReactNode, useEffect } from 'react';
import { useUserStore } from '../../store/userStore';

interface AuthContextType {
  isAuthenticated: boolean;
  isLoading: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider = ({ children }: { children: ReactNode }) => {
  const { isAuthenticated, isLoading, setLoading } = useUserStore();

  useEffect(() => {
    // Placeholder for actual auth check
    const checkAuth = async () => {
      // Simulate network request
      setTimeout(() => {
        setLoading(false);
      }, 500);
    };

    checkAuth();
  }, [setLoading]);

  return (
    <AuthContext.Provider value={{ isAuthenticated, isLoading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
