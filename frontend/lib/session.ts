// Persistência da sessão (localStorage) + eventos globais usados pelo cliente HTTP, pelo mock e pelo AuthProvider.
import type { TokenOut, User } from "./types";

export const TOKEN_KEY = "asclepio.token";
export const REFRESH_KEY = "asclepio.refresh";
export const EXPIRES_KEY = "asclepio.expires_at";
export const USER_KEY = "asclepio.user";

/** Disparado quando a sessão é inválida e não pôde ser renovada → AuthProvider redireciona para /login. */
export const UNAUTHORIZED_EVENT = "asclepio:unauthorized";
/** Disparado em HTTP 428 (troca de senha obrigatória ou MFA obrigatório). */
export const PRECONDITION_EVENT = "asclepio:precondition";
/** Disparado quando tokens são renovados (refresh) para o AuthProvider sincronizar o estado. */
export const SESSION_EVENT = "asclepio:session";

export type PreconditionKind = "password" | "mfa";

const hasWindow = () => typeof window !== "undefined";

export function getToken(): string | null {
  return hasWindow() ? localStorage.getItem(TOKEN_KEY) : null;
}
export function getRefreshToken(): string | null {
  return hasWindow() ? localStorage.getItem(REFRESH_KEY) : null;
}
/** Epoch (ms) de expiração do access token, ou null. */
export function getExpiresAt(): number | null {
  if (!hasWindow()) return null;
  const v = localStorage.getItem(EXPIRES_KEY);
  const n = v ? Number(v) : NaN;
  return Number.isFinite(n) ? n : null;
}
export function getStoredUser(): User | null {
  if (!hasWindow()) return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as User) : null;
  } catch {
    return null;
  }
}

export function saveSession(tok: TokenOut) {
  if (!hasWindow()) return;
  localStorage.setItem(TOKEN_KEY, tok.access_token);
  localStorage.setItem(REFRESH_KEY, tok.refresh_token);
  localStorage.setItem(EXPIRES_KEY, String(Date.now() + tok.expires_in * 1000));
  localStorage.setItem(USER_KEY, JSON.stringify(tok.user));
  window.dispatchEvent(new CustomEvent(SESSION_EVENT, { detail: tok }));
}
export function saveUser(user: User) {
  if (!hasWindow()) return;
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}
export function clearSession() {
  if (!hasWindow()) return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_KEY);
  localStorage.removeItem(EXPIRES_KEY);
  localStorage.removeItem(USER_KEY);
}

export function notifyUnauthorized() {
  clearSession();
  if (hasWindow()) window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
}
export function notifyPrecondition(kind: PreconditionKind) {
  if (hasWindow()) window.dispatchEvent(new CustomEvent<PreconditionKind>(PRECONDITION_EVENT, { detail: kind }));
}
