/**
 * Client cabinet session context.
 *
 * The session lives in an HttpOnly Django cookie — the provider only
 * holds the profile payload from ``/api/auth/me/`` for UI state. Nothing
 * auth-related goes to localStorage (plan-client-auth §2).
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { accountApi, type ClientSession } from "./api";

type AuthState = {
  session: ClientSession | null;
  loading: boolean;
  refresh: () => Promise<void>;
  logout: () => Promise<void>;
};

const AuthContext = createContext<AuthState>({
  session: null,
  loading: true,
  refresh: async () => {},
  logout: async () => {},
});

export function AccountAuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<ClientSession | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    try {
      const me = await accountApi.me();
      setSession(me);
    } catch {
      setSession(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    // Fetch the csrftoken cookie first so later POSTs pass CSRF checks.
    void accountApi.csrf().catch(() => {});
    accountApi
      .me()
      .then((me) => {
        if (!cancelled) setSession(me);
      })
      .catch(() => {
        if (!cancelled) setSession(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const logout = useCallback(async () => {
    try {
      await accountApi.logout();
    } finally {
      setSession(null);
    }
  }, []);

  const value = useMemo(
    () => ({ session, loading, refresh, logout }),
    [session, loading, refresh, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAccountAuth(): AuthState {
  return useContext(AuthContext);
}
