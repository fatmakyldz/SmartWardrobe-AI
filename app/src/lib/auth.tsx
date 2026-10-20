import { useQueryClient } from '@tanstack/react-query';
import { createContext, ReactNode, useCallback, useContext, useEffect, useMemo, useState } from 'react';

import { api, refreshSession, Session, setRefreshedHandler, setSession, setUnauthorizedHandler, User } from './api';
import { useI18n } from './i18n';
import { readRefreshToken, writeRefreshToken } from './tokenStore';

type AuthCtx = {
  ready: boolean;
  user: User | null;
  signIn: (s: Session) => Promise<void>;
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

  // Local sign-out: forget the session here (the server side is already dead or being revoked).
  const clear = useCallback(async () => {
    setSession({ access: null, refresh: null });
    await writeRefreshToken(null);
    setUserState(null);
    qc.clear();
  }, [qc]);

  const signOut = useCallback(async () => {
    await api.logout().catch(() => undefined); // revokes this device's refresh token / clears the cookie
    await clear();
  }, [clear]);

  const signIn = useCallback(
    async (s: Session) => {
      setSession(s);
      await writeRefreshToken(s.refresh);
      setUser(s.user);
    },
    [setUser],
  );

  useEffect(() => {
    setUnauthorizedHandler(() => void clear());
    // Each refresh spends the stored token: keep the new one.
    setRefreshedHandler((s) => void writeRefreshToken(s.refresh));
    (async () => {
      // Access tokens are never stored, so every start begins with a refresh (cookie on the web).
      const saved = await readRefreshToken();
      setSession({ access: null, refresh: saved });
      try {
        const s = await refreshSession();
        if (s) setUser(s.user);
        else await clear();
      } catch {
        // offline: stay signed out for now; the stored refresh token is kept for the next start
        setSession({ access: null, refresh: saved });
      }
      setReady(true);
    })();
  }, [setUser, clear]);

  const value = useMemo(() => ({ ready, user, signIn, signOut, setUser }), [ready, user, signIn, signOut, setUser]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthCtx {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth outside AuthProvider');
  return ctx;
}
