"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import type { MfaChallenge, Role, TokenOut, User } from "@/lib/types";
import { isMfaChallenge } from "@/lib/types";
import { api, refreshSession } from "@/lib/api";
import {
  clearSession, getExpiresAt, getRefreshToken, getStoredUser, getToken, PRECONDITION_EVENT, saveSession, saveUser, SESSION_EVENT, UNAUTHORIZED_EVENT,
  type PreconditionKind,
} from "@/lib/session";

export type LoginResult = { kind: "ok"; token: TokenOut } | { kind: "mfa"; challenge: MfaChallenge };

type AuthState = {
  user: User | null;
  token: string | null;
  ready: boolean;
  /** Etapa 1 do login. Retorna `mfa` quando o usuário tem MFA ativo (chamar `verifyMfa`). */
  login: (email: string, password: string) => Promise<LoginResult>;
  /** Etapa 2 do login (TOTP de 6 dígitos ou código de recuperação). */
  verifyMfa: (mfa_token: string, code: string) => Promise<TokenOut>;
  /** Encerra a sessão atual (revoga o refresh token no backend) e limpa tudo. */
  logout: () => Promise<void>;
  /** Encerra TODAS as sessões do usuário (inclusive esta). */
  logoutAll: () => Promise<number>;
  /** Recarrega `GET /auth/me` (após trocar senha, ativar MFA etc.). */
  refreshUser: () => Promise<User | null>;
  hasRole: (...roles: Role[]) => boolean;
  /** Troca de senha obrigatória (primeiro acesso / reset pelo admin). */
  mustChangePassword: boolean;
  /** Admin sem MFA: o backend bloqueia tudo com 428 até configurar. */
  mfaSetupRequired: boolean;
};

const AuthContext = createContext<AuthState | null>(null);

/** Renova proativamente quando faltar menos que isto para o access token expirar. */
const REFRESH_AHEAD_MS = 2 * 60_000;
const REFRESH_CHECK_MS = 30_000;

export function AuthProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);

  // Hidrata a sessão do localStorage (sistema externo) e escuta eventos do cliente HTTP
  useEffect(() => {
    const hydrate = () => {
      setToken(getToken());
      setUser(getStoredUser());
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
    const onSession = (e: Event) => {
      const tok = (e as CustomEvent<TokenOut>).detail;
      if (tok?.access_token) setToken(tok.access_token);
      if (tok?.user) setUser(tok.user);
    };
    const onPrecondition = (e: Event) => {
      const kind = (e as CustomEvent<PreconditionKind>).detail;
      const target = kind === "mfa" ? "/conta/mfa" : "/conta/senha?forced=1";
      // Sincroniza o usuário (flags) e leva para a tela obrigatória
      setUser((u) => (u ? { ...u, ...(kind === "mfa" ? { mfa_enabled: false } : { must_change_password: true }) } : u));
      if (!window.location.pathname.startsWith(target.split("?")[0])) router.replace(target);
    };
    const id = window.setTimeout(hydrate, 0);
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
    window.addEventListener(SESSION_EVENT, onSession);
    window.addEventListener(PRECONDITION_EVENT, onPrecondition);
    return () => {
      window.clearTimeout(id);
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized);
      window.removeEventListener(SESSION_EVENT, onSession);
      window.removeEventListener(PRECONDITION_EVENT, onPrecondition);
    };
  }, [router]);

  const refreshUser = useCallback(async () => {
    try {
      const u = await api.auth.me();
      setUser(u);
      saveUser(u);
      return u;
    } catch {
      /* 401/428 já tratados no cliente */
      return null;
    }
  }, []);

  // Revalida o usuário com o backend quando há token (silencioso)
  useEffect(() => {
    if (!ready || !token) return;
    let cancelled = false;
    api.auth
      .me()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        saveUser(u);
      })
      .catch(() => {
        /* 401/428 já tratados no cliente (eventos) */
      });
    return () => {
      cancelled = true;
    };
  }, [ready, token]);

  // Renovação proativa do access token (< 2 min para expirar) — também ao voltar para a aba
  useEffect(() => {
    if (!ready || !token) return;
    const check = () => {
      if (document.visibilityState === "hidden") return;
      const exp = getExpiresAt();
      if (exp != null && exp - Date.now() < REFRESH_AHEAD_MS && getRefreshToken()) void refreshSession();
    };
    check();
    const id = window.setInterval(check, REFRESH_CHECK_MS);
    document.addEventListener("visibilitychange", check);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", check);
    };
  }, [ready, token]);

  const applyToken = useCallback((tok: TokenOut) => {
    saveSession(tok);
    setToken(tok.access_token);
    setUser(tok.user);
  }, []);

  const login = useCallback(
    async (email: string, password: string): Promise<LoginResult> => {
      const res = await api.auth.login(email, password);
      if (isMfaChallenge(res)) return { kind: "mfa", challenge: res };
      applyToken(res);
      return { kind: "ok", token: res };
    },
    [applyToken],
  );

  const verifyMfa = useCallback(
    async (mfa_token: string, code: string) => {
      const tok = await api.auth.mfaVerify(mfa_token, code);
      applyToken(tok);
      return tok;
    },
    [applyToken],
  );

  const logout = useCallback(async () => {
    const refresh_token = getRefreshToken();
    try {
      await api.auth.logout({ refresh_token });
    } catch {
      /* sessão já inválida — ignorar */
    }
    clearSession();
    setToken(null);
    setUser(null);
  }, []);

  const logoutAll = useCallback(async () => {
    let revoked = 0;
    try {
      const r = await api.auth.logoutAll();
      revoked = r.revoked;
    } finally {
      clearSession();
      setToken(null);
      setUser(null);
    }
    return revoked;
  }, []);

  const hasRole = useCallback((...roles: Role[]) => !!user && roles.includes(user.role), [user]);

  const mustChangePassword = !!user?.must_change_password;
  const mfaSetupRequired = !!user && user.role === "admin" && !user.mfa_enabled && !mustChangePassword;

  const value = useMemo<AuthState>(
    () => ({ user, token, ready, login, verifyMfa, logout, logoutAll, refreshUser, hasRole, mustChangePassword, mfaSetupRequired }),
    [user, token, ready, login, verifyMfa, logout, logoutAll, refreshUser, hasRole, mustChangePassword, mfaSetupRequired],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth deve ser usado dentro de <AuthProvider>");
  return ctx;
}
