// Cliente HTTP tipado contra docs/CONTRATO_API.md (v1 + auth v1.1). Em NEXT_PUBLIC_USE_MOCK=true usa lib/mock.
import type { StreamEvent, TokenOut } from "./types";
import type { ApiClient, ApiError as ApiErrorT, StreamHandler } from "./api-types";
import { mockApi } from "./mock";
import {
  clearSession, getRefreshToken, getToken, notifyPrecondition, notifyUnauthorized, saveSession, TOKEN_KEY, USER_KEY, UNAUTHORIZED_EVENT,
} from "./session";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
// Re-exportados por compatibilidade (implementação em lib/session.ts)
export { TOKEN_KEY, USER_KEY, UNAUTHORIZED_EVENT, getToken, clearSession };

export class ApiError extends Error implements ApiErrorT {
  status: number;
  detail: string;
  code?: string;
  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

export function isApiError(e: unknown): e is ApiErrorT {
  return typeof e === "object" && e !== null && "status" in e && "detail" in e;
}

export function errorMessage(e: unknown, fallback = "Erro inesperado"): string {
  if (isApiError(e)) return e.detail || fallback;
  if (e instanceof Error) return e.message || fallback;
  return fallback;
}

// ---- Refresh com mutex: várias requisições em 401 simultâneas disparam UM único POST /auth/refresh ----
let refreshing: Promise<TokenOut | null> | null = null;

/**
 * Renova a sessão com o refresh token guardado. Resolve com o novo TokenOut ou null.
 * Se o backend recusar o refresh (401/403) a sessão é limpa e o AuthProvider é notificado.
 */
export function refreshSession(): Promise<TokenOut | null> {
  if (refreshing) return refreshing;
  const rt = getRefreshToken();
  if (!rt) return Promise.resolve(null);
  refreshing = api.auth
    .refresh(rt)
    .then((tok) => {
      saveSession(tok);
      return tok;
    })
    .catch((e: unknown) => {
      if (isApiError(e) && (e.status === 401 || e.status === 403 || e.status === 422)) notifyUnauthorized();
      return null;
    })
    .finally(() => {
      refreshing = null;
    });
  return refreshing;
}

/** Interpreta o corpo de erro (FastAPI): `detail` string/lista e `code` opcional. */
async function parseError(res: Response): Promise<{ detail: string; code?: string }> {
  let detail = res.statusText || `Erro ${res.status}`;
  let code: string | undefined;
  try {
    const j = await res.json();
    if (typeof j?.detail === "string") detail = j.detail;
    else if (Array.isArray(j?.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    else if (typeof j?.detail?.detail === "string") detail = j.detail.detail;
    if (typeof j?.code === "string") code = j.code;
    else if (typeof j?.detail?.code === "string") code = j.detail.code;
  } catch {
    /* corpo não-JSON */
  }
  return { detail, code };
}

/** 428 Precondition Required: troca de senha obrigatória ou MFA obrigatório (admin). */
function handlePrecondition(detail: string, code?: string) {
  notifyPrecondition(code === "mfa_required_setup" ? "mfa" : "password");
  return new ApiError(428, detail, code);
}

function qs(params?: Record<string, string | number | boolean | null | undefined>) {
  if (!params) return "";
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "") return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}

type ReqOpts = { auth?: boolean; retried?: boolean };

async function request<T>(path: string, init: RequestInit = {}, opts: ReqOpts = {}): Promise<T> {
  const headers = new Headers(init.headers);
  if (!headers.has("Content-Type") && init.body) headers.set("Content-Type", "application/json");
  headers.set("Accept", "application/json");
  const token = getToken();
  if (opts.auth !== false && token) headers.set("Authorization", `Bearer ${token}`);
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { ...init, headers, cache: "no-store" });
  } catch {
    throw new ApiError(0, "Não foi possível conectar à API. Verifique se o backend está em execução.");
  }
  if (res.status === 401 && opts.auth !== false) {
    // Tenta renovar UMA vez e repete a requisição; se falhar, limpa a sessão e redireciona para /login.
    if (!opts.retried) {
      const tok = await refreshSession();
      if (tok) return request<T>(path, init, { ...opts, retried: true });
    }
    notifyUnauthorized();
    throw new ApiError(401, "Sessão expirada. Faça login novamente.");
  }
  if (!res.ok) {
    const { detail, code } = await parseError(res);
    if (res.status === 428 && opts.auth !== false) throw handlePrecondition(detail, code);
    throw new ApiError(res.status, detail, code);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const patch = <T>(path: string, body?: unknown) => request<T>(path, { method: "PATCH", body: body === undefined ? undefined : JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

/** Parser manual de SSE sobre fetch (EventSource não suporta POST). */
async function streamSse(path: string, body: unknown, onEvent: StreamHandler, signal?: AbortSignal, retried = false): Promise<void> {
  const headers: Record<string, string> = { "Content-Type": "application/json", Accept: "text/event-stream" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { method: "POST", headers, body: JSON.stringify(body), signal, cache: "no-store" });
  } catch (e) {
    if ((e as Error)?.name === "AbortError") throw e;
    throw new ApiError(0, "Não foi possível conectar à API.");
  }
  if (res.status === 401) {
    if (!retried) {
      const tok = await refreshSession();
      if (tok) return streamSse(path, body, onEvent, signal, true);
    }
    notifyUnauthorized();
    throw new ApiError(401, "Sessão expirada.");
  }
  if (!res.ok || !res.body) {
    const { detail, code } = await parseError(res);
    if (res.status === 428) throw handlePrecondition(detail, code);
    throw new ApiError(res.status, detail || "Falha no stream", code);
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder("utf-8");
  let buffer = "";
  const dispatch = (block: string) => {
    let event = "message";
    const dataLines: string[] = [];
    for (const raw of block.split(/\r?\n/)) {
      if (!raw || raw.startsWith(":")) continue;
      const idx = raw.indexOf(":");
      const field = idx === -1 ? raw : raw.slice(0, idx);
      let value = idx === -1 ? "" : raw.slice(idx + 1);
      if (value.startsWith(" ")) value = value.slice(1);
      if (field === "event") event = value;
      else if (field === "data") dataLines.push(value);
    }
    if (!dataLines.length) return;
    const dataStr = dataLines.join("\n");
    let data: unknown = dataStr;
    try {
      data = JSON.parse(dataStr);
    } catch {
      /* manter string */
    }
    onEvent({ event, data } as StreamEvent);
  };
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let sep: number;
    while ((sep = buffer.search(/\r?\n\r?\n/)) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep).replace(/^\r?\n\r?\n/, "");
      dispatch(block);
    }
  }
  if (buffer.trim()) dispatch(buffer);
}

export const httpApi: ApiClient = {
  health: () => get("/health"),
  publicConfig: () => request("/public/config", {}, { auth: false }),
  auth: {
    login: (email, password) => request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, { auth: false }),
    mfaVerify: (mfa_token, code) => request("/auth/mfa/verify", { method: "POST", body: JSON.stringify({ mfa_token, code }) }, { auth: false }),
    // refresh NÃO passa pelo fluxo de retry (auth:false) — o próprio refresh token é a credencial
    refresh: (refresh_token) => request("/auth/refresh", { method: "POST", body: JSON.stringify({ refresh_token }) }, { auth: false }),
    me: () => get("/auth/me"),
    logout: (body) => post("/auth/logout", { refresh_token: body?.refresh_token ?? undefined }),
    logoutAll: () => post("/auth/logout-all"),
    changePassword: (current_password, new_password) => post("/auth/change-password", { current_password, new_password }),
    mfaSetup: () => get("/auth/mfa/setup"),
    mfaEnable: (code) => post("/auth/mfa/enable", { code }),
    mfaDisable: (password, code) => post("/auth/mfa/disable", { password, code }),
    sessions: () => get("/auth/sessions"),
    revokeSession: (id) => del(`/auth/sessions/${id}`),
  },
  users: {
    list: (params) => get(`/users${qs({ role: params?.role || undefined, active: params?.active === "" || params?.active === undefined ? undefined : params.active, q: params?.q || undefined })}`),
    get: (id) => get(`/users/${id}`),
    create: (input) => post("/users", input),
    update: (id, body) => patch(`/users/${id}`, body),
    resetPassword: (id) => post(`/users/${id}/reset-password`),
    mfaReset: (id) => post(`/users/${id}/mfa/reset`),
  },
  catalog: {
    specialties: (includeInactive) => get(`/catalog/specialties${qs({ include_inactive: includeInactive ? true : undefined })}`),
    createSpecialty: (input) => post("/catalog/specialties", input),
    updateSpecialty: (id, body) => patch(`/catalog/specialties/${id}`, body),
    deleteSpecialty: (id) => del(`/catalog/specialties/${id}`),
    sectors: (includeInactive) => get(`/catalog/sectors${qs({ include_inactive: includeInactive ? true : undefined })}`),
    createSector: (input) => post("/catalog/sectors", input),
    updateSector: (id, body) => patch(`/catalog/sectors/${id}`, body),
    deleteSector: (id) => del(`/catalog/sectors/${id}`),
  },
  dashboard: { stats: () => get("/dashboard/stats") },
  patients: {
    list: (params) => get(`/patients${qs(params)}`),
    get: (id) => get(`/patients/${id}`),
    pendingExams: (id) => get(`/patients/${id}/pending-exams`),
    context: (id) => get(`/patients/${id}/context`),
  },
  assistant: {
    chat: (req) => post("/assistant/chat", req),
    stream: (req, onEvent, signal) => streamSse("/assistant/chat/stream", req, onEvent, signal),
    conversations: () => get("/assistant/conversations"),
    conversation: (id) => get(`/assistant/conversations/${encodeURIComponent(id)}`),
    deleteConversation: (id) => del(`/assistant/conversations/${encodeURIComponent(id)}`),
    feedback: (req) => post("/assistant/feedback", req),
    suggestions: (patientId) => get(`/assistant/suggestions${qs({ patient_id: patientId ?? undefined })}`),
    graph: () => get("/assistant/graph"),
  },
  workflows: {
    clinicalReview: (patient_id, reason) => post("/workflows/clinical-review", { patient_id, reason: reason || undefined }),
    decision: (run_id, approved, comment) => post(`/workflows/runs/${encodeURIComponent(run_id)}/decision`, { approved, comment: comment || undefined }),
    runs: (params) => get(`/workflows/runs${qs(params)}`),
    run: (run_id) => get(`/workflows/runs/${encodeURIComponent(run_id)}`),
    graph: () => get("/workflows/graph"),
  },
  alerts: {
    list: (params) => get(`/alerts${qs(params)}`),
    ack: (id) => post(`/alerts/${id}/ack`),
  },
  knowledge: {
    documents: (doc_type) => get(`/knowledge/documents${qs({ doc_type })}`),
    document: (id) => get(`/knowledge/documents/${encodeURIComponent(id)}`),
    search: (query, k = 5, doc_type) => post("/knowledge/search", { query, k, doc_type: doc_type || undefined }),
    reindex: () => post("/knowledge/reindex"),
  },
  model: {
    info: () => get("/model/info"),
    switch: (model) => post("/model/switch", { model }),
  },
  audit: {
    list: (params) => get(`/audit${qs(params)}`),
    get: (id) => get(`/audit/${id}`),
    verify: () => get("/audit/verify"),
    actions: () => get("/audit/actions"),
  },
};

export const api: ApiClient = USE_MOCK ? mockApi : httpApi;
