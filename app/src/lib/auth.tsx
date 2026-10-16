import { useQueryClient } from '@tanstack/react-query';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, setToken, setUnauthorizedHandler, User } from './api';
import { useI18n } from './i18n';
import { readToken, writeToken } from './tokenStore';

type AuthCtx = {
  ready: boolean;
  user: User | null;
  signIn: (token: string, user: User) => Promise<void>;
  signOut: () => Promise<void>;
  setUser: (u: User) => void;
};

const AuthContext = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUserState] = useState<User | null>(null);
  const { setLang } = useI18n();
  const qc = useQueryClient();

  const setUser = useCallback(
    (u: User) => {
      setUserState(u);
      setLang(u.locale);
    },
    [setLang],
  );

  const signOut = useCallback(async () => {
    setToken(null);
    await writeToken(null);
    setUserState(null);
    qc.clear();
  }, [qc]);

  const signIn = useCallback(
    async (token: string, u: User) => {
      setToken(token);
      await writeToken(token);
      setUser(u);
    },
    [setUser],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => void signOut());
    (async () => {
      const saved = await readToken();
      if (saved) {
        setToken(saved);
        try {
          setUser(await api.me());
        } catch {
          setToken(null);
          await writeToken(null);
        }
      }
      setReady(true);
    })();
  }, [setUser, signOut]);

  const value = useMemo(() => ({ ready, user, signIn, signOut, setUser }), [ready, user, signIn, signOut, setUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
