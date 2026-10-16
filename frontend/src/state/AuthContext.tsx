import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";

import { setTokenGetter } from "@/api/client";
import type { TokenResponse, User } from "@/api/types";
import * as endpoints from "@/api/endpoints";

/**
 * Sign-in is intentionally scoped to the browser tab session.
 * The token lives in `sessionStorage`, so closing the tab/browser clears it
 * (no cross-restart "remember me" persistence).
 */
const TOKEN_KEY = "cc.token";

type AuthStatus = "loading" | "authenticated" | "anonymous";

interface AuthContextValue {
  user: User | null;
  token: string | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => sessionStorage.getItem(TOKEN_KEY));
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>("loading");
  const tokenRef = useRef<string | null>(token);

  // Wire the API client's bearer-token getter exactly once.
  useEffect(() => {
    setTokenGetter(() => tokenRef.current);
  }, []);

  useEffect(() => {
    tokenRef.current = token;
  }, [token]);

  const applySession = useCallback((res: TokenResponse) => {
    sessionStorage.setItem(TOKEN_KEY, res.access_token);
    tokenRef.current = res.access_token;
    setToken(res.access_token);
    setUser(res.user);
    setStatus("authenticated");
  }, []);

  const clearSession = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    tokenRef.current = null;
    setToken(null);
    setUser(null);
    setStatus("anonymous");
  }, []);

  // Validate any stored token on first mount.
  useEffect(() => {
    let cancelled = false;
    const stored = sessionStorage.getItem(TOKEN_KEY);
    if (!stored) {
      setStatus("anonymous");
      return;
    }
    tokenRef.current = stored;
    (async () => {
      try {
        const me = await endpoints.getMe();
        if (cancelled) return;
        setUser({ id: me.id, name: me.name, email: me.email });
        setStatus("authenticated");
      } catch {
        if (cancelled) return;
        sessionStorage.removeItem(TOKEN_KEY);
        tokenRef.current = null;
        setToken(null);
        setUser(null);
        setStatus("anonymous");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(
    async (email: string, password: string) => {
      const res = await endpoints.login(email, password);
      applySession(res);
    },
    [applySession],
  );

  const signup = useCallback(
    async (name: string, email: string, password: string) => {
      const res = await endpoints.signup(name, email, password);
      applySession(res);
    },
    [applySession],
  );

  const logout = useCallback(() => clearSession(), [clearSession]);

  return (
    <AuthContext.Provider value={{ user, token, status, login, signup, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
