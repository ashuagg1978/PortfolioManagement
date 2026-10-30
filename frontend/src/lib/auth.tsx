import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { AUTH_EXPIRED_EVENT, getMe, getToken, login as apiLogin, setToken } from './api';
import type { AuthUser } from '../types/api';

interface AuthState {
  user: AuthUser | null;
  /** True while a stored token is being validated on first load. */
  loading: boolean;
  signIn: (username: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(() => getToken() !== null);

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
    // Cached data belongs to the previous user - never show it to the next one.
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    if (getToken() === null) return;
    getMe()
      .then(setUser)
      .catch(() => setToken(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    window.addEventListener(AUTH_EXPIRED_EVENT, signOut);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, signOut);
  }, [signOut]);

  const signIn = useCallback(
    async (username: string, password: string) => {
      const result = await apiLogin(username, password);
      queryClient.clear();
      setToken(result.access_token);
      setUser(result.user);
    },
    [queryClient],
  );

  return <AuthContext.Provider value={{ user, loading, signIn, signOut }}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
