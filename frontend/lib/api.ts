// Cliente HTTP tipado contra docs/CONTRATO_API.md. Em NEXT_PUBLIC_USE_MOCK=true usa lib/mock.
import type { StreamEvent } from "./types";
import type { ApiClient, ApiError as ApiErrorT, StreamHandler } from "./api-types";
import { mockApi } from "./mock";

export const API_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1").replace(/\/$/, "");
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
export const TOKEN_KEY = "asclepio.token";
export const USER_KEY = "asclepio.user";

export class ApiError extends Error implements ApiErrorT {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
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

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearSession() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export const UNAUTHORIZED_EVENT = "asclepio:unauthorized";

/** Limpa a sessão e notifica o AuthProvider (que redireciona para /login). */
function handleUnauthorized() {
  clearSession();
  if (typeof window !== "undefined") window.dispatchEvent(new CustomEvent(UNAUTHORIZED_EVENT));
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

async function request<T>(path: string, init: RequestInit = {}, opts: { auth?: boolean } = {}): Promise<T> {
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
    handleUnauthorized();
    throw new ApiError(401, "Sessão expirada. Faça login novamente.");
  }
  if (!res.ok) {
    let detail = res.statusText || `Erro ${res.status}`;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") detail = j.detail;
      else if (Array.isArray(j?.detail)) detail = j.detail.map((d: { msg?: string }) => d.msg ?? JSON.stringify(d)).join("; ");
    } catch {
      /* corpo não-JSON */
    }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

const get = <T>(path: string) => request<T>(path);
const post = <T>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
const del = <T>(path: string) => request<T>(path, { method: "DELETE" });

/** Parser manual de SSE sobre fetch (EventSource não suporta POST). */
async function streamSse(path: string, body: unknown, onEvent: StreamHandler, signal?: AbortSignal): Promise<void> {
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
    handleUnauthorized();
    throw new ApiError(401, "Sessão expirada.");
  }
  if (!res.ok || !res.body) {
    let detail = res.statusText;
    try {
      const j = await res.json();
      if (typeof j?.detail === "string") detail = j.detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail || "Falha no stream");
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
  auth: {
    login: (email, password) => request("/auth/login", { method: "POST", body: JSON.stringify({ email, password }) }, { auth: false }),
    me: () => get("/auth/me"),
    logout: () => post("/auth/logout"),
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
