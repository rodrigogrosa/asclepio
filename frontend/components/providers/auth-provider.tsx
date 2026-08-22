"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { Role, User } from "@/lib/types";
import { useRouter } from "next/navigation";
import { api, TOKEN_KEY, USER_KEY, UNAUTHORIZED_EVENT } from "@/lib/api";

type AuthState = {
  user: User | null;
  token: string | null;
  ready: boolean;
  login: (email: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  hasRole: (...roles: Role[]) => boolean;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // Hidrata a sessão do localStorage (sistema externo) e escuta 401 do cliente HTTP
  useEffect(() => {
    const hydrate = () => {
      try {
        const t = localStorage.getItem(TOKEN_KEY);
        const u = localStorage.getItem(USER_KEY);
        if (t) setToken(t);
        if (u) setUser(JSON.parse(u) as User);
      } catch {
        /* ignore */
      }
      setReady(true);
    };
    const onUnauthorized = () => {
      setToken(null);
      setUser(null);
      if (!window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        router.replace(`/login?next=${next}`);
      }
    };
    const id = window.setTimeout(hydrate, 0);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    };
  }, [router]);

  // Revalida o usuário com o backend quando há token (silencioso)
  useEffect(() => {
    if (!ready || !token) return;
    let cancelled = false;
    api.auth
      .me()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        localStorage.setItem(USER_KEY, JSON.stringify(u));
      })
      .catch(() => {
        /* 401 já tratado no cliente (redireciona) */
      });
    return () => {
      cancelled = true;
    };
  }, [ready, token]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await api.auth.login(email, password);
    localStorage.setItem(TOKEN_KEY, res.access_token);
    localStorage.setItem(USER_KEY, JSON.stringify(res.user));
    setToken(res.access_token);
    setUser(res.user);
    return res.user;
  }, []);

  const logout = useCallback(async () => {
    try {
      await api.auth.logout();
    } catch {
      /* token stateless — ignorar */
    }
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
    setToken(null);
    setUser(null);
  }, []);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user]);

  const value = useMemo(() => ({ user, token, ready, login, logout, hasRole }), [user, token, ready, login, logout, hasRole]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de <AuthProvider>");
  return ctx;
}
