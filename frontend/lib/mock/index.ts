// Implementação MOCK do cliente de API — mesmos contratos, dados locais (lib/mock/data.ts)
import type {
  Alert, AuditEntry, AuditListResponse, AuditVerifyResponse, ChatMessage, ChatRequest, ChatResponse, Conversation,
  ConversationDetail, DashboardStats, Exam, FeedbackRequest, HealthResponse, KnowledgeDocument, KnowledgeDocumentDetail,
  KnowledgeSearchResponse, LoginResponse, ModelInfoResponse, Patient, PatientContext, PatientDetail, ReindexResponse,
  StreamEvent, User, WorkflowGraph, WorkflowRun, Guardrail, Citation, Intent, TokenOut, Session, MfaSetup, MfaEnableResponse,
  UserCreateInput, UserUpdateInput, UserCreateResponse, UsersListParams, PublicConfig, Specialty, Sector, SpecialtyInput, SectorInput,
  DocsHubList, HubDocumentContent, HubDocument,
} from "@/lib/types";
import type { ApiClient, ApiError as ApiErrorT } from "@/lib/api-types";
import {
  ALERTS, AUDIT, AUDIT_ACTIONS, CHAT_GRAPH_MERMAID, CITATIONS, CONVERSATIONS, CONV_MESSAGES, KNOWLEDGE_DOCS, MODEL_ACTIVE, MODEL_INFO,
  PATIENTS, PATIENT_DETAILS, RUNS, SUGGESTIONS_GENERIC, SUGGESTIONS_PATIENT, USERS, WORKFLOW_GRAPH, citationsFor, knowledgeDetail,
  MOCK_TOTP_CODE, PERMISSIONS_BY_ROLE, PUBLIC_CONFIG, SPECIALTIES, SECTORS, HUB_CATEGORIES, HUB_CONTENTS, type MockUser,
} from "./data";
import { initials, sleep, uid } from "@/lib/utils";
import { getStoredUser, notifyPrecondition } from "@/lib/session";
import { hasPermission, type Permission } from "@/lib/permissions";

class MockApiError extends Error implements ApiErrorT {
  status: number;
  detail: string;
  code?: string;
  constructor(status: number, detail: string, code?: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

// Estado mutável em memória (dura enquanto a aba estiver aberta)
const state = {
  alerts: ALERTS.map((a) => ({ ...a })),
  conversations: CONVERSATIONS.map((c) => ({ ...c })),
  messages: Object.fromEntries(Object.entries(CONV_MESSAGES).map(([k, v]) => [k, v.map((m) => ({ ...m }))])) as Record<string, ChatMessage[]>,
  runs: RUNS.map((r) => ({ ...r })),
  model: { ...MODEL_INFO, active: { ...MODEL_ACTIVE } },
  nextMsgId: 5000,
  currentUser: null as User | null,
  // ---- auth v1.1 (mock) ----
  users: USERS.map((u) => ({ ...u, recovery_codes: [...u.recovery_codes] })) as MockUser[],
  sessions: [] as MockSession[],
  mfaChallenges: new Map<string, { userId: number; attempts: number; expires: number }>(),
  pendingMfa: new Map<number, string>(), // userId → secret em ativação
  nextUserId: 100,
  nextSessionId: 1000,
  specialties: SPECIALTIES.map((x) => ({ ...x })) as Specialty[],
  sectors: SECTORS.map((x) => ({ ...x })) as Sector[],
  nextCatalogId: 500,
};

type MockSession = { id: number; userId: number; refresh: string; created_at: string; last_used_at: string | null; expires_at: string; ip: string | null; user_agent: string | null };

const latency = (min = 120, max = 420) => sleep(min + Math.random() * (max - min));

/** Remove campos privados do usuário mock. */
function publicUser(u: MockUser): User {
  const { password: _p, totp_secret: _s, recovery_codes: _r, ...rest } = u;
  void _p;
  void _s;
  void _r;
  return rest;
}

function findUserByEmail(email: string) {
  return state.users.find((x) => x.email.toLowerCase() === email.trim().toLowerCase());
}

/** Usuário autenticado atual (estado em memória → localStorage → fallback). Sempre reflete o registro vivo em state.users. */
function currentMockUser(): MockUser {
  const ref = state.currentUser ?? getStoredUser();
  const live = ref ? state.users.find((u) => u.id === ref.id) ?? findUserByEmail(ref.email) : undefined;
  return live ?? state.users.find((u) => u.email === "dra.ana@asclepio.fiap") ?? state.users[0];
}
function currentUser(): User {
  return publicUser(currentMockUser());
}

const b64 = (s: string) => (typeof btoa === "function" ? btoa(unescape(encodeURIComponent(s))) : s);
const unb64 = (s: string) => {
  try {
    return typeof atob === "function" ? decodeURIComponent(escape(atob(s))) : s;
  } catch {
    return "";
  }
};

const ACCESS_TTL = 1800; // 30 min
const REFRESH_TTL = 12 * 3600; // 12 h

function issueTokens(u: MockUser): TokenOut {
  const sid = state.nextSessionId++;
  const refresh = `mockrt.${b64(u.email)}.${sid}.${Math.random().toString(36).slice(2, 12)}`;
  const now = Date.now();
  state.sessions.push({
    id: sid,
    userId: u.id,
    refresh,
    created_at: new Date(now).toISOString(),
    last_used_at: new Date(now).toISOString(),
    expires_at: new Date(now + REFRESH_TTL * 1000).toISOString(),
    ip: "127.0.0.1",
    user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "mock",
  });
  u.last_login_at = new Date(now).toISOString();
  state.currentUser = publicUser(u);
  return {
    access_token: `mock.${b64(u.email)}.${sid}.${now}`,
    refresh_token: refresh,
    token_type: "bearer",
    expires_in: ACCESS_TTL,
    refresh_expires_in: REFRESH_TTL,
    user: publicUser(u),
    must_change_password: u.must_change_password,
  };
}

/** Sessão atual no mock (derivada do refresh token salvo). */
function currentSessionId(): number | null {
  if (typeof window === "undefined") return null;
  const rt = localStorage.getItem("asclepio.refresh");
  const parts = rt?.split(".") ?? [];
  const sid = Number(parts[2]);
  return Number.isFinite(sid) ? sid : null;
}

/** Garante que a sessão atual exista em memória (após reload da aba o estado se perde). */
function ensureCurrentSession(u: MockUser) {
  const sid = currentSessionId();
  if (sid == null) return;
  if (!state.sessions.some((s) => s.id === sid)) {
    const now = Date.now();
    state.sessions.push({ id: sid, userId: u.id, refresh: localStorage.getItem("asclepio.refresh") ?? "", created_at: new Date(now - 3600_000).toISOString(), last_used_at: new Date(now).toISOString(), expires_at: new Date(now + REFRESH_TTL * 1000).toISOString(), ip: "127.0.0.1", user_agent: typeof navigator !== "undefined" ? navigator.userAgent : "mock" });
    // uma segunda sessão "de outro dispositivo" para a demo
    state.sessions.push({ id: sid + 5000, userId: u.id, refresh: "", created_at: new Date(now - 2 * 86400_000).toISOString(), last_used_at: new Date(now - 5 * 3600_000).toISOString(), expires_at: new Date(now + 3 * 3600_000).toISOString(), ip: "10.20.1.12", user_agent: "Mozilla/5.0 (iPhone; CPU iPhone OS 17_4 like Mac OS X) Safari/604.1" });
    if (sid > state.nextSessionId) state.nextSessionId = sid + 1;
  }
}

const isTotp = (code: string) => /^\d{6}$/.test(code.replace(/\s/g, ""));
const normRecovery = (code: string) => code.trim().toUpperCase().replace(/[^A-Z0-9]/g, "").replace(/^(.{4})(.{4})$/, "$1-$2");

function checkMfaCode(u: MockUser, code: string): boolean {
  const c = code.trim();
  if (isTotp(c)) return c.replace(/\s/g, "") === MOCK_TOTP_CODE;
  const rc = normRecovery(c);
  const idx = u.recovery_codes.indexOf(rc);
  if (idx === -1) return false;
  u.recovery_codes.splice(idx, 1); // uso único
  return true;
}

function randomSecret(len = 16) {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let out = "";
  for (let i = 0; i < len; i++) out += alphabet[Math.floor(Math.random() * alphabet.length)];
  return out;
}
function randomRecoveryCodes(n = 10) {
  const alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";
  const chunk = () => Array.from({ length: 4 }, () => alphabet[Math.floor(Math.random() * alphabet.length)]).join("");
  return Array.from({ length: n }, () => `${chunk()}-${chunk()}`);
}
function randomTempPassword() {
  const U = "ABCDEFGHJKLMNPQRSTUVWXYZ", L = "abcdefghijkmnopqrstuvwxyz", D = "23456789", S = "!@#$%&*";
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  const all = U + L + D + S;
  const arr = [pick(U), pick(L), pick(D), pick(S), ...Array.from({ length: 10 }, () => pick(all))];
  return arr.sort(() => Math.random() - 0.5).join("");
}

/** SVG "QR" determinístico para exibição (não é um QR real — o backend gera o verdadeiro). */
function fakeQrSvg(seed: string) {
  let h = 2166136261;
  const rnd = () => {
    h ^= h << 13; h >>>= 0; h ^= h >> 17; h ^= h << 5; h >>>= 0;
    return (h % 1000) / 1000;
  };
  for (const ch of seed) h = (h ^ ch.charCodeAt(0)) * 16777619;
  const n = 29, cell = 6, pad = 12;
  const size = n * cell + pad * 2;
  const rects: string[] = [];
  const finder = (x: number, y: number) => {
    rects.push(`<rect x="${pad + x * cell}" y="${pad + y * cell}" width="${7 * cell}" height="${7 * cell}" fill="#0b0b10"/>`);
    rects.push(`<rect x="${pad + (x + 1) * cell}" y="${pad + (y + 1) * cell}" width="${5 * cell}" height="${5 * cell}" fill="#fff"/>`);
    rects.push(`<rect x="${pad + (x + 2) * cell}" y="${pad + (y + 2) * cell}" width="${3 * cell}" height="${3 * cell}" fill="#0b0b10"/>`);
  };
  for (let y = 0; y < n; y++)
    for (let x = 0; x < n; x++) {
      const inFinder = (x < 8 && y < 8) || (x > n - 9 && y < 8) || (x < 8 && y > n - 9);
      if (inFinder) continue;
      if (rnd() < 0.48) rects.push(`<rect x="${pad + x * cell}" y="${pad + y * cell}" width="${cell}" height="${cell}" fill="#0b0b10"/>`);
    }
  finder(0, 0); finder(n - 7, 0); finder(0, n - 7);
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" role="img" aria-label="QR code TOTP (mock)"><rect width="100%" height="100%" fill="#fff"/>${rects.join("")}</svg>`;
}

function passwordPolicyError(pw: string): string | null {
  if (pw.length < 10) return "A senha deve ter pelo menos 10 caracteres";
  if (!/[A-Z]/.test(pw)) return "A senha deve conter letra maiúscula";
  if (!/[a-z]/.test(pw)) return "A senha deve conter letra minúscula";
  if (!/\d/.test(pw)) return "A senha deve conter dígito";
  if (!/[^A-Za-z0-9]/.test(pw)) return "A senha deve conter símbolo";
  return null;
}

/** Regras 428 do backend: troca de senha obrigatória / MFA obrigatório para admin (em todas as rotas exceto /auth/*). */
function assertPrecondition() {
  const u = currentMockUser();
  if (u.must_change_password) {
    notifyPrecondition("password");
    throw new MockApiError(428, "Troca de senha obrigatória", "must_change_password");
  }
  if (u.role === "admin" && !u.mfa_enabled) {
    notifyPrecondition("mfa");
    throw new MockApiError(428, "MFA obrigatório para administradores", "mfa_required_setup");
  }
}
function requireAdmin() {
  requirePerm("users:manage", "Apenas administradores podem gerenciar usuários");
}
function requirePerm(perm: Permission, msg = "Você não tem permissão para esta ação") {
  if (!hasPermission(currentMockUser(), perm)) throw new MockApiError(403, msg);
}

const CRM_RE = /^(CRM\s?)?\d{4,7}-[A-Z]{2}$/i;
/** Normaliza para "CRM 123456-UF". */
function normalizeCrm(v: string) {
  const m = v.trim().toUpperCase().replace(/\s+/g, " ").match(/^(?:CRM\s?)?(\d{4,7})-([A-Z]{2})$/);
  return m ? `CRM ${m[1]}-${m[2]}` : v.trim();
}
function validateProfessional(role: User["role"], crm: string | null | undefined, specialty_id: number | null | undefined) {
  if (role !== "medico") return;
  if (!crm || !CRM_RE.test(crm.trim())) throw new MockApiError(422, "CRM obrigatório para médicos no formato CRM 123456-UF");
  if (!specialty_id) throw new MockApiError(422, "Especialidade obrigatória para médicos");
}
function specialtyName(id: number | null | undefined) {
  return id ? state.specialties.find((s) => s.id === id)?.name ?? null : null;
}
function recountCatalog() {
  state.specialties.forEach((sp) => (sp.professionals_count = state.users.filter((u) => u.specialty_id === sp.id && u.is_active).length));
  state.sectors.forEach((sc) => (sc.patients_count = PATIENTS.filter((p) => p.ward === sc.name).length));
}
recountCatalog();

function detectIntent(message: string, patientId?: number | null): Intent {
  const m = message.toLowerCase();
  if (/ignore|esque[çc]a|instru[çc][õo]es anteriores|cpf|endere[çc]o|telefone|senha/.test(m)) return "fora_escopo";
  if (/prescri|dose|mg|posologia/.test(m)) return "prescricao";
  if (/modelo|evolu[çc][ãa]o soap|sum[áa]rio de alta|documento/.test(m)) return "documento";
  if (patientId || /paciente|exame pendente|evolu[çc][ãa]o/.test(m)) return "paciente";
  if (/protocolo|bundle|crit[ée]rio|sepse|cetoacidose|avc|ic |insufici/.test(m)) return "protocolo";
  return "geral";
}

function buildAnswer(req: ChatRequest): { answer: string; citations: Citation[]; guardrail: Guardrail; intent: Intent; blocked: boolean } {
  const intent = detectIntent(req.message, req.patient_id);
  if (intent === "fora_escopo") {
    const injection = /ignore|esque[çc]a|instru[çc][õo]es/.test(req.message.toLowerCase());
    return {
      blocked: true,
      intent,
      citations: [],
      guardrail: {
        status: "bloqueado",
        flags: injection ? ["prompt_injection", "pii_request"] : ["pii_request"],
        notes: injection ? ["Padrão de prompt injection detectado", "Solicitação de dados pessoais sensíveis"] : ["Solicitação de dados pessoais sensíveis"],
        pii_redacted: 0,
        injection_detected: injection,
      },
      answer:
        "Solicitação bloqueada pelo guardrail de entrada. O Asclépio não expõe dados pessoais identificáveis (CPF, endereço, telefone) e não aceita instruções que tentem alterar seu comportamento.\n\nPosso ajudar com dúvidas clínicas, protocolos institucionais ou com o resumo **anonimizado** do paciente.",
    };
  }
  const p = req.patient_id ? PATIENT_DETAILS[req.patient_id] : null;
  const m = req.message.toLowerCase();
  let citations: Citation[] = [];
  let answer = "";
  if (/sepse|lactato|bundle|hemocultura/.test(m)) {
    citations = citationsFor([1, 2, 3]);
    answer = `De acordo com o **Protocolo Institucional de Sepse (v3.2)**, o pacote da 1ª hora inclui [1]:\n\n1. Dosar **lactato** (repetir em 2–4h se > 2 mmol/L) [2]\n2. Coletar **hemoculturas (2 amostras)** antes do antibiótico [3]\n3. **Antibiótico** de amplo espectro em até 1h\n4. **Cristaloide 30 mL/kg** se hipotensão ou lactato ≥ 4 mmol/L\n5. **Noradrenalina** se PAM < 65 mmHg durante/após reposição\n\n${p ? `**Aplicado ao paciente em contexto** (${p.ward} · ${p.bed}): ${p.exams.filter((e) => e.status === "atrasado").length ? `há exame(s) atrasado(s) — ${p.exams.filter((e) => e.status === "atrasado").map((e) => e.name).join(", ")}.` : "não há exames atrasados."}` : ""}\n\n> Sugestões do Asclépio são apoio à decisão e exigem validação de um profissional habilitado.`;
  } else if (/pot[áa]ssio|hipercalemia|k /.test(m)) {
    citations = citationsFor([5, 3]);
    answer = `Valores de potássio **< 2,5** ou **> 6,0 mEq/L** são considerados críticos e exigem comunicação imediata [2]. Em pacientes com IC em uso de IECA + antagonista mineralocorticoide, com K > 5,5 mEq/L o protocolo sugere suspender temporariamente o ARM, realizar ECG e repetir potássio em 4–6h [1].`;
  } else if (/cetoacidose|cad|gasometria|insulina/.test(m)) {
    citations = citationsFor([4]);
    answer = `No protocolo de **cetoacidose diabética**, a gasometria e os eletrólitos devem ser repetidos a cada **2–4 horas** até resolução (pH > 7,30, HCO3 ≥ 18, ânion gap normalizado) [1]. Potássio deve ser reposto se < 5,2 mEq/L antes da insulina; suspender insulina se K < 3,3 [1].`;
  } else if (/glasgow|avc|neurol/.test(m)) {
    citations = citationsFor([7]);
    answer = `Queda **≥ 2 pontos na Escala de Coma de Glasgow** (ou ≥ 4 no NIHSS) em paciente com AVC isquêmico indica **TC de crânio imediata** para excluir transformação hemorrágica ou edema com efeito de massa [1]. Recomenda-se avaliação neurológica urgente e monitorização horária.`;
  } else if (/tropon|dor tor[áa]cica|sca|infarto/.test(m)) {
    citations = citationsFor([6]);
    answer = `O protocolo de dor torácica prevê **troponina ultrassensível 0/3h** [1]. Delta ≥ 20% ou valor acima do percentil 99 com clínica compatível sugere IAM sem supra e indica acionar a cardiologia [1].`;
  } else if (p && /pendente|atrasad|priorit|exame/.test(m)) {
    const pend = p.exams.filter((e) => e.status === "pendente" || e.status === "atrasado");
    citations = citationsFor([3]);
    answer = `**Exames pendentes/atrasados do paciente em contexto** (${pend.length}):\n\n${pend.map((e) => `- ${e.status === "atrasado" ? "⚠️ **ATRASADO** — " : ""}${e.name} (${e.category})`).join("\n") || "- Nenhum exame pendente."}\n\nPrazos segundo o FAQ do laboratório [1]. Priorize os atrasados e os ligados a valores críticos recentes.`;
  } else if (p && /evolu|resum|24h|últimas/.test(m)) {
    const last = p.notes[p.notes.length - 1];
    const v = p.vitals[p.vitals.length - 1];
    citations = [];
    answer = `**Resumo anonimizado das últimas 24h** — ${p.primary_diagnosis}, ${p.ward}/${p.bed}:\n\n- Sinais vitais mais recentes: FC ${v.hr} bpm · PA ${v.sbp}/${v.dbp} mmHg · FR ${v.rr} irpm · T ${v.temp_c.toFixed(1)} °C · SpO₂ ${v.spo2}%${v.gcs != null ? ` · Glasgow ${v.gcs}` : ""}\n- Última evolução (${last.author}): ${last.text}\n- Exames críticos: ${p.exams.filter((e) => e.is_critical).map((e) => `${e.name} ${e.result_value ?? ""} ${e.unit ?? ""}`).join("; ") || "nenhum"}\n- Alertas ativos: ${p.alerts.filter((a) => !a.acknowledged_at).length}\n\n> Resumo gerado a partir do contexto anonimizado — validar no prontuário.`;
  } else if (p && /intera|medica/.test(m)) {
    citations = citationsFor([5]);
    answer = `Medicações em uso: ${p.medications.filter((x) => x.status === "ativo").map((x) => `**${x.name}** ${x.dose} ${x.route} ${x.frequency}`).join("; ")}.\n\n${p.id === 2 ? "Atenção à associação **espironolactona + enalapril** em paciente com DRC e K 5,9 — risco de hipercalemia [1]." : "Não identifiquei interações de alto risco nas fontes disponíveis; recomenda-se conferência com a farmácia clínica."}`;
  } else {
    citations = citationsFor([1, 3]);
    answer = `Com base na base de conhecimento institucional, aqui está um resumo sobre **"${req.message.trim().slice(0, 80)}"**:\n\n- Os protocolos institucionais priorizam identificação precoce e reavaliação seriada [1].\n- Prazos e valores críticos de exames seguem o FAQ do laboratório [2].\n- Para orientação específica de um paciente, selecione o **contexto do paciente** acima para que eu use o resumo anonimizado.\n\n> Sugestões do Asclépio são apoio à decisão e exigem validação de um profissional habilitado.`;
  }
  const guardrail: Guardrail = {
    status: p ? "ajustado" : "aprovado",
    flags: p ? ["pii_redacted"] : [],
    notes: p ? ["3 campos de PII redigidos do contexto do paciente", "Citações verificadas contra a base"] : ["Sem PII detectada", "Citações verificadas contra a base"],
    pii_redacted: p ? 3 : 0,
    injection_detected: false,
  };
  return { answer, citations, guardrail, intent, blocked: false };
}

function persistChat(req: ChatRequest, built: ReturnType<typeof buildAnswer>, latency_ms: number): ChatResponse {
  let conv = req.conversation_id ? state.conversations.find((c) => c.id === req.conversation_id) : undefined;
  const now = new Date().toISOString();
  if (!conv) {
    const p = req.patient_id ? PATIENTS.find((x) => x.id === req.patient_id) : null;
    conv = {
      id: uid("conv"),
      title: req.message.trim().slice(0, 60) + (req.message.length > 60 ? "…" : ""),
      patient_id: p?.id ?? null,
      patient_name: p?.name ?? null,
      created_at: now,
      updated_at: now,
      message_count: 0,
    };
    state.conversations.unshift(conv);
    state.messages[conv.id] = [];
  }
  const userMsg: ChatMessage = { id: state.nextMsgId++, role: "user", content: req.message, created_at: now, citations: [], guardrail: null, intent: null, latency_ms: null, feedback: null };
  const asstMsg: ChatMessage = { id: state.nextMsgId++, role: "assistant", content: built.answer, created_at: new Date().toISOString(), citations: built.citations, guardrail: built.guardrail, intent: built.intent, latency_ms, feedback: null };
  state.messages[conv.id].push(userMsg, asstMsg);
  conv.message_count += 2;
  conv.updated_at = asstMsg.created_at;
  return {
    conversation_id: conv.id,
    message_id: asstMsg.id,
    answer: built.answer,
    citations: built.citations,
    guardrail: built.guardrail,
    intent: built.intent,
    model: state.model.active,
    latency_ms,
    trace_id: uid("trc"),
    confidence: built.blocked ? "baixa" : built.citations.length >= 2 ? "alta" : "media",
    patient_id: req.patient_id ?? conv.patient_id ?? null,
  };
}

function healthNow(): HealthResponse {
  return { status: "ok", version: PUBLIC_CONFIG.version, env: "mock", llm: { provider: "ollama", model: state.model.active.name, reachable: true }, embeddings: { provider: "ollama", model: "nomic-embed-text" }, db: "ok", vectorstore: { chunks: 156 } };
}

const rawMockApi: ApiClient = {
  async health(): Promise<HealthResponse> {
    await latency();
    return healthNow();
  },
  async publicConfig(): Promise<PublicConfig> {
    await latency(50, 150);
    return { ...PUBLIC_CONFIG };
  },
  auth: {
    async login(email, password): Promise<LoginResponse> {
      await latency(300, 700);
      const u = findUserByEmail(email);
      if (!u || u.password !== password) throw new MockApiError(401, "E-mail ou senha inválidos");
      if (!u.is_active) throw new MockApiError(423, "Usuário desativado. Procure o administrador.");
      if (u.mfa_enabled) {
        const mfa_token = `mfa.${uid("chal")}`;
        state.mfaChallenges.set(mfa_token, { userId: u.id, attempts: 0, expires: Date.now() + 300_000 });
        return { mfa_required: true, mfa_token, expires_in: 300, methods: ["totp", "recovery_code"] };
      }
      return issueTokens(u);
    },
    async mfaVerify(mfa_token, code): Promise<TokenOut> {
      await latency(250, 600);
      const ch = state.mfaChallenges.get(mfa_token);
      if (!ch || ch.expires < Date.now()) throw new MockApiError(401, "Desafio MFA expirado. Faça login novamente.");
      const u = state.users.find((x) => x.id === ch.userId);
      if (!u) throw new MockApiError(401, "Desafio MFA inválido");
      if (!checkMfaCode(u, code)) {
        ch.attempts += 1;
        if (ch.attempts >= 5) {
          state.mfaChallenges.delete(mfa_token);
          throw new MockApiError(401, "Limite de tentativas excedido. Faça login novamente.");
        }
        throw new MockApiError(401, `Código inválido (${5 - ch.attempts} tentativa(s) restante(s))`);
      }
      state.mfaChallenges.delete(mfa_token);
      return issueTokens(u);
    },
    async refresh(refresh_token): Promise<TokenOut> {
      await latency(100, 250);
      const parts = refresh_token.split(".");
      if (parts[0] !== "mockrt") throw new MockApiError(401, "Refresh token inválido");
      const u = findUserByEmail(unb64(parts[1] ?? ""));
      if (!u || !u.is_active) throw new MockApiError(401, "Refresh token inválido");
      const sid = Number(parts[2]);
      const sess = state.sessions.find((s) => s.id === sid);
      // Rotação: revoga a sessão antiga (se conhecida) e emite nova
      if (sess) state.sessions = state.sessions.filter((s) => s.id !== sid);
      return issueTokens(u);
    },
    async me(): Promise<User> {
      await latency(50, 150);
      const u = currentMockUser();
      ensureCurrentSession(u);
      return publicUser(u);
    },
    async logout(body) {
      await latency(50, 150);
      const rt = body?.refresh_token;
      if (rt) state.sessions = state.sessions.filter((s) => s.refresh !== rt);
      state.currentUser = null;
      return { ok: true as const };
    },
    async logoutAll() {
      await latency(100, 250);
      const u = currentMockUser();
      const n = state.sessions.filter((s) => s.userId === u.id).length;
      state.sessions = state.sessions.filter((s) => s.userId !== u.id);
      state.currentUser = null;
      return { ok: true as const, revoked: n };
    },
    async changePassword(current_password, new_password) {
      await latency(300, 600);
      const u = currentMockUser();
      if (u.password !== current_password) throw new MockApiError(400, "Senha atual incorreta");
      const err = passwordPolicyError(new_password);
      if (err) throw new MockApiError(422, err);
      if (new_password === current_password) throw new MockApiError(422, "A nova senha deve ser diferente da atual");
      u.password = new_password;
      u.must_change_password = false;
      // revoga as OUTRAS sessões
      const sid = currentSessionId();
      state.sessions = state.sessions.filter((s) => s.userId !== u.id || s.id === sid);
      state.currentUser = publicUser(u);
      return { ok: true as const };
    },
    async mfaSetup(): Promise<MfaSetup> {
      await latency(200, 500);
      const u = currentMockUser();
      if (u.mfa_enabled) throw new MockApiError(400, "MFA já está ativo para este usuário");
      const secret = state.pendingMfa.get(u.id) ?? randomSecret();
      state.pendingMfa.set(u.id, secret);
      const label = encodeURIComponent(`Asclépio:${u.email}`);
      const otpauth_uri = `otpauth://totp/${label}?secret=${secret}&issuer=${encodeURIComponent("Asclépio")}&algorithm=SHA1&digits=6&period=30`;
      return { secret, otpauth_uri, qr_svg: fakeQrSvg(otpauth_uri) };
    },
    async mfaEnable(code): Promise<MfaEnableResponse> {
      await latency(250, 600);
      const u = currentMockUser();
      const secret = state.pendingMfa.get(u.id);
      if (!secret) throw new MockApiError(400, "Inicie a configuração do MFA antes de ativar");
      if (!isTotp(code) || code.replace(/\s/g, "") !== MOCK_TOTP_CODE) throw new MockApiError(401, "Código inválido. Verifique o horário do dispositivo e tente novamente.");
      u.totp_secret = secret;
      u.mfa_enabled = true;
      u.recovery_codes = randomRecoveryCodes(10);
      state.pendingMfa.delete(u.id);
      state.currentUser = publicUser(u);
      return { ok: true as const, recovery_codes: [...u.recovery_codes] };
    },
    async mfaDisable(password, code) {
      await latency(250, 600);
      const u = currentMockUser();
      if (!u.mfa_enabled) throw new MockApiError(400, "MFA não está ativo");
      if (u.role === "admin") throw new MockApiError(400, "Administradores não podem desativar o MFA");
      if (u.password !== password) throw new MockApiError(401, "Senha incorreta");
      if (!checkMfaCode(u, code)) throw new MockApiError(401, "Código inválido");
      u.mfa_enabled = false;
      u.totp_secret = null;
      u.recovery_codes = [];
      state.currentUser = publicUser(u);
      return { ok: true as const };
    },
    async sessions(): Promise<Session[]> {
      await latency(150, 350);
      const u = currentMockUser();
      ensureCurrentSession(u);
      const sid = currentSessionId();
      return state.sessions
        .filter((s) => s.userId === u.id)
        .map((s) => ({ id: s.id, created_at: s.created_at, last_used_at: s.last_used_at, expires_at: s.expires_at, ip: s.ip, user_agent: s.user_agent, current: s.id === sid }))
        .sort((a, b) => Number(b.current) - Number(a.current) || b.created_at.localeCompare(a.created_at));
    },
    async revokeSession(id) {
      await latency(150, 350);
      const u = currentMockUser();
      const s = state.sessions.find((x) => x.id === id && x.userId === u.id);
      if (!s) throw new MockApiError(404, "Sessão não encontrada");
      state.sessions = state.sessions.filter((x) => x.id !== id);
      return { ok: true as const };
    },
  },
  users: {
    async list(params?: UsersListParams): Promise<User[]> {
      await latency();
      requireAdmin();
      const q = (params?.q ?? "").trim().toLowerCase();
      return state.users
        .filter((u) => (!params?.role || u.role === params.role) && (params?.active === undefined || params.active === "" || u.is_active === params.active) && (!q || u.name.toLowerCase().includes(q) || u.email.toLowerCase().includes(q) || (u.crm ?? "").toLowerCase().includes(q)))
        .map(publicUser)
        .sort((a, b) => a.id - b.id);
    },
    async get(id: number): Promise<User> {
      await latency();
      requireAdmin();
      const u = state.users.find((x) => x.id === id);
      if (!u) throw new MockApiError(404, "Usuário não encontrado");
      return publicUser(u);
    },
    async create(input: UserCreateInput): Promise<UserCreateResponse> {
      await latency(300, 600);
      requireAdmin();
      const email = input.email.trim().toLowerCase();
      if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) throw new MockApiError(422, "E-mail inválido");
      if (findUserByEmail(email)) throw new MockApiError(409, "Já existe um usuário com este e-mail");
      if (!input.name.trim()) throw new MockApiError(422, "Nome é obrigatório");
      validateProfessional(input.role, input.crm, input.specialty_id);
      if (input.specialty_id && !state.specialties.some((sp) => sp.id === input.specialty_id && sp.active)) throw new MockApiError(422, "Especialidade inválida");
      if (input.sector_id && !state.sectors.some((sc) => sc.id === input.sector_id)) throw new MockApiError(422, "Setor inválido");
      let temporary_password: string | null = null;
      let password = input.password ?? "";
      if (!password) {
        temporary_password = randomTempPassword();
        password = temporary_password;
      } else {
        const err = passwordPolicyError(password);
        if (err) throw new MockApiError(422, err);
      }
      const u: MockUser = {
        id: state.nextUserId++,
        name: input.name.trim(),
        email,
        role: input.role,
        crm: input.crm?.trim() ? (input.role === "medico" ? normalizeCrm(input.crm) : input.crm.trim()) : null,
        specialty: specialtyName(input.specialty_id) ?? input.specialty?.trim() ?? null,
        specialty_id: input.specialty_id ?? null,
        sector_id: input.sector_id ?? null,
        avatar_initials: initials(input.name) || "??",
        permissions: PERMISSIONS_BY_ROLE[input.role],
        mfa_enabled: false,
        must_change_password: true,
        is_active: true,
        is_demo: false,
        last_login_at: null,
        created_at: new Date().toISOString(),
        password,
        totp_secret: null,
        recovery_codes: [],
      };
      state.users.push(u);
      recountCatalog();
      return { user: publicUser(u), temporary_password };
    },
    async update(id: number, patch: UserUpdateInput): Promise<User> {
      await latency(250, 500);
      requireAdmin();
      const me = currentMockUser();
      const u = state.users.find((x) => x.id === id);
      if (!u) throw new MockApiError(404, "Usuário não encontrado");
      if (u.id === me.id && patch.role && patch.role !== "admin") throw new MockApiError(400, "Você não pode remover o próprio papel de administrador");
      if (u.id === me.id && patch.is_active === false) throw new MockApiError(400, "Você não pode desativar a própria conta");
      if (patch.name !== undefined) {
        u.name = patch.name.trim() || u.name;
        u.avatar_initials = initials(u.name) || u.avatar_initials;
      }
      if (patch.role !== undefined) {
        u.role = patch.role;
        u.permissions = PERMISSIONS_BY_ROLE[patch.role];
      }
      const nextRole = patch.role ?? u.role;
      const nextCrm = patch.crm !== undefined ? patch.crm : u.crm;
      const nextSpec = patch.specialty_id !== undefined ? patch.specialty_id : u.specialty_id;
      validateProfessional(nextRole, nextCrm, nextSpec);
      if (patch.crm !== undefined) u.crm = patch.crm?.trim() ? (nextRole === "medico" ? normalizeCrm(patch.crm) : patch.crm.trim()) : null;
      if (patch.specialty_id !== undefined) {
        if (patch.specialty_id && !state.specialties.some((sp) => sp.id === patch.specialty_id)) throw new MockApiError(422, "Especialidade inválida");
        u.specialty_id = patch.specialty_id;
        u.specialty = specialtyName(patch.specialty_id);
      } else if (patch.specialty !== undefined) u.specialty = patch.specialty?.trim() || null;
      if (patch.sector_id !== undefined) {
        if (patch.sector_id && !state.sectors.some((sc) => sc.id === patch.sector_id)) throw new MockApiError(422, "Setor inválido");
        u.sector_id = patch.sector_id;
      }
      if (patch.is_active !== undefined) {
        u.is_active = patch.is_active;
        if (!u.is_active) state.sessions = state.sessions.filter((s) => s.userId !== u.id);
      }
      recountCatalog();
      return publicUser(u);
    },
    async resetPassword(id: number) {
      await latency(300, 600);
      requireAdmin();
      const u = state.users.find((x) => x.id === id);
      if (!u) throw new MockApiError(404, "Usuário não encontrado");
      const temporary_password = randomTempPassword();
      u.password = temporary_password;
      u.must_change_password = true;
      state.sessions = state.sessions.filter((s) => s.userId !== u.id);
      return { temporary_password };
    },
    async mfaReset(id: number) {
      await latency(250, 500);
      requireAdmin();
      const u = state.users.find((x) => x.id === id);
      if (!u) throw new MockApiError(404, "Usuário não encontrado");
      u.mfa_enabled = false;
      u.totp_secret = null;
      u.recovery_codes = [];
      state.pendingMfa.delete(u.id);
      return { ok: true as const };
    },
  },
  docsHub: {
    async list(): Promise<DocsHubList> {
      await latency(120, 300);
      requirePerm("docs:read");
      const categories = HUB_CATEGORIES.map((c) => ({ ...c, documents: c.documents.map((d) => ({ ...d })) }));
      return { categories, total: categories.reduce((s, c) => s + c.documents.length, 0) };
    },
    async read(id: string): Promise<HubDocumentContent> {
      await latency(150, 400);
      requirePerm("docs:read");
      const doc = HUB_CATEGORIES.flatMap((c) => c.documents).find((d) => d.id === id);
      if (!doc) throw new MockApiError(404, "Documento não encontrado");
      if (!doc.readable) throw new MockApiError(400, "Este documento não está disponível para leitura — use o download");
      return { ...doc, content: HUB_CONTENTS[id] ?? `# ${doc.title}\n\n_Conteúdo de exemplo._` };
    },
    downloadUrl(id: string): string {
      return `/docs-hub/${encodeURIComponent(id)}/download`;
    },
    async download(id: string): Promise<{ blob: Blob; filename: string }> {
      await latency(200, 500);
      requirePerm("docs:read");
      const doc: HubDocument | undefined = HUB_CATEGORIES.flatMap((c) => c.documents).find((d) => d.id === id);
      if (!doc) throw new MockApiError(404, "Documento não encontrado");
      if (!doc.downloadable) throw new MockApiError(400, "Download indisponível para este documento");
      if (doc.format === "pdf") {
        // PDF mínimo válido (uma página em branco com título) para a demo
        const pdf = `%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj\n4 0 obj<</Length 68>>stream\nBT /F1 18 Tf 72 780 Td (Asclepio - ${doc.title.replace(/[()\\]/g, "")}) Tj ET\nendstream endobj\n5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF`;
        return { blob: new Blob([pdf], { type: "application/pdf" }), filename: doc.filename };
      }
      const content = HUB_CONTENTS[id] ?? `# ${doc.title}`;
      return { blob: new Blob([content], { type: "text/plain;charset=utf-8" }), filename: doc.filename };
    },
  },
  catalog: {
    async specialties(includeInactive?: boolean): Promise<Specialty[]> {
      await latency(80, 200);
      requirePerm("catalog:read");
      recountCatalog();
      return state.specialties.filter((x) => includeInactive || x.active).map((x) => ({ ...x })).sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
    },
    async createSpecialty(input): Promise<Specialty> {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const name = input.name.trim();
      if (!name) throw new MockApiError(422, "Nome é obrigatório");
      if (state.specialties.some((x) => x.name.toLowerCase() === name.toLowerCase())) throw new MockApiError(409, "Já existe uma especialidade com este nome");
      const sp: Specialty = { id: state.nextCatalogId++, name, code: input.code?.trim().toUpperCase() || null, active: true, professionals_count: 0 };
      state.specialties.push(sp);
      return { ...sp };
    },
    async updateSpecialty(id, patch: SpecialtyInput): Promise<Specialty> {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const sp = state.specialties.find((x) => x.id === id);
      if (!sp) throw new MockApiError(404, "Especialidade não encontrada");
      if (patch.name !== undefined) {
        const name = patch.name.trim();
        if (!name) throw new MockApiError(422, "Nome é obrigatório");
        if (state.specialties.some((x) => x.id !== id && x.name.toLowerCase() === name.toLowerCase())) throw new MockApiError(409, "Já existe uma especialidade com este nome");
        sp.name = name;
        state.users.filter((u) => u.specialty_id === id).forEach((u) => (u.specialty = name));
      }
      if (patch.code !== undefined) sp.code = patch.code?.trim().toUpperCase() || null;
      if (patch.active !== undefined) sp.active = patch.active;
      return { ...sp };
    },
    async deleteSpecialty(id) {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const sp = state.specialties.find((x) => x.id === id);
      if (!sp) throw new MockApiError(404, "Especialidade não encontrada");
      recountCatalog();
      if (sp.professionals_count > 0) throw new MockApiError(409, `Há ${sp.professionals_count} profissional(is) vinculado(s). Desative em vez de remover.`);
      state.specialties = state.specialties.filter((x) => x.id !== id);
      return { ok: true as const };
    },
    async sectors(includeInactive?: boolean): Promise<Sector[]> {
      await latency(80, 200);
      requirePerm("catalog:read");
      recountCatalog();
      return state.sectors.filter((x) => includeInactive || x.active).map((x) => ({ ...x })).sort((a, b) => a.name.localeCompare(b.name, "pt-BR"));
    },
    async createSector(input): Promise<Sector> {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const name = input.name.trim();
      if (!name) throw new MockApiError(422, "Nome é obrigatório");
      if (state.sectors.some((x) => x.name.toLowerCase() === name.toLowerCase())) throw new MockApiError(409, "Já existe um setor com este nome");
      const sc: Sector = { id: state.nextCatalogId++, name, kind: input.kind, active: true, patients_count: 0 };
      state.sectors.push(sc);
      return { ...sc };
    },
    async updateSector(id, patch: SectorInput): Promise<Sector> {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const sc = state.sectors.find((x) => x.id === id);
      if (!sc) throw new MockApiError(404, "Setor não encontrado");
      if (patch.name !== undefined) {
        const name = patch.name.trim();
        if (!name) throw new MockApiError(422, "Nome é obrigatório");
        if (state.sectors.some((x) => x.id !== id && x.name.toLowerCase() === name.toLowerCase())) throw new MockApiError(409, "Já existe um setor com este nome");
        sc.name = name;
      }
      if (patch.kind !== undefined) sc.kind = patch.kind;
      if (patch.active !== undefined) sc.active = patch.active;
      return { ...sc };
    },
    async deleteSector(id) {
      await latency(200, 400);
      requirePerm("catalog:manage");
      const sc = state.sectors.find((x) => x.id === id);
      if (!sc) throw new MockApiError(404, "Setor não encontrado");
      recountCatalog();
      if (sc.patients_count > 0) throw new MockApiError(409, `Há ${sc.patients_count} paciente(s) internado(s) neste setor. Desative em vez de remover.`);
      state.sectors = state.sectors.filter((x) => x.id !== id);
      return { ok: true as const };
    },
  },
  dashboard: {
    async stats(): Promise<DashboardStats> {
      await latency();
      const me = currentMockUser();
      const dist = { baixo: 0, moderado: 0, alto: 0, critico: 0 };
      PATIENTS.forEach((p) => dist[p.risk_level]++);
      const canModel = hasPermission(me, "model:read");
      const canAudit = hasPermission(me, "audit:read");
      const clinical = hasPermission(me, "workflows:run") && !hasPermission(me, "settings:read");
      const openAlerts = state.alerts.filter((a) => !a.acknowledged_at);
      return {
        patients: PATIENTS.length,
        patients_critical: dist.critico,
        pending_exams: PATIENTS.reduce((s, p) => s + p.pending_exams_count, 0),
        overdue_exams: PATIENTS.reduce((s, p) => s + p.overdue_exams_count, 0),
        open_alerts: openAlerts.length,
        chats_today: 14,
        workflows_today: state.runs.length,
        guardrail_blocks_today: canAudit ? 2 : null,
        model: canModel ? state.model.active : null,
        system: hasPermission(me, "settings:read") ? healthNow() : null,
        my_work: clinical
          ? {
              pending_approvals: state.runs.filter((r) => r.status === "aguardando_aprovacao").map((r) => ({ ...r, steps: [] })),
              my_open_alerts: openAlerts.length,
              my_conversations_today: state.conversations.filter((c) => new Date(c.updated_at).toDateString() === new Date().toDateString()).length || 3,
            }
          : null,
        recent_alerts: [...state.alerts].sort((a, b) => b.created_at.localeCompare(a.created_at)).slice(0, 5),
        recent_runs: [...state.runs].sort((a, b) => b.started_at.localeCompare(a.started_at)).slice(0, 5).map((r) => ({ ...r, steps: [] })),
        risk_distribution: dist,
      };
    },
  },
  patients: {
    async list(params): Promise<Patient[]> {
      await latency();
      const q = (params?.search ?? "").trim().toLowerCase();
      return PATIENTS.filter((p) => (!q || p.name.toLowerCase().includes(q) || p.mrn.toLowerCase().includes(q) || p.primary_diagnosis.toLowerCase().includes(q)) && (!params?.ward || p.ward === params.ward) && (!params?.risk || p.risk_level === params.risk));
    },
    async get(id): Promise<PatientDetail> {
      await latency();
      const d = PATIENT_DETAILS[id];
      if (!d) throw new MockApiError(404, "Paciente não encontrado");
      return { ...d, alerts: state.alerts.filter((a) => a.patient_id === id) };
    },
    async pendingExams(id): Promise<Exam[]> {
      await latency();
      const d = PATIENT_DETAILS[id];
      if (!d) throw new MockApiError(404, "Paciente não encontrado");
      return d.exams.filter((e) => e.status === "pendente" || e.status === "atrasado");
    },
    async context(id): Promise<PatientContext> {
      await latency(200, 500);
      const d = PATIENT_DETAILS[id];
      if (!d) throw new MockApiError(404, "Paciente não encontrado");
      const v = d.vitals[d.vitals.length - 1];
      const txt = [
        `## CONTEXTO CLÍNICO ANONIMIZADO (paciente [REDIGIDO], MRN [REDIGIDO])`,
        `Sexo: ${d.sex === "F" ? "feminino" : "masculino"} · Idade: ${d.age} anos · Data de nascimento: [REDIGIDO]`,
        `Setor/leito: ${d.ward} / ${d.bed} · Internação há ${Math.max(1, Math.round((Date.now() - new Date(d.admission_date).getTime()) / 86_400_000))} dia(s)`,
        `Diagnóstico principal: ${d.primary_diagnosis}`,
        `Comorbidades: ${d.comorbidities.join(", ") || "nenhuma"} · Alergias: ${d.allergies.join(", ") || "nenhuma"}`,
        `Peso/altura: ${d.weight_kg} kg / ${d.height_cm} cm · Tipo sanguíneo: ${d.blood_type}`,
        ``,
        `### Sinais vitais mais recentes`,
        `FC ${v.hr} bpm · PA ${v.sbp}/${v.dbp} mmHg · FR ${v.rr} irpm · Temp ${v.temp_c.toFixed(1)} °C · SpO2 ${v.spo2}%${v.gcs != null ? ` · Glasgow ${v.gcs}` : ""}`,
        ``,
        `### Exames`,
        ...d.exams.map((e) => `- ${e.name} [${e.status}${e.is_critical ? ", CRÍTICO" : ""}]${e.result_value ? `: ${e.result_value} ${e.unit ?? ""} (ref ${e.reference_range ?? "—"})` : ""}`),
        ``,
        `### Medicações ativas`,
        ...d.medications.filter((m) => m.status === "ativo").map((m) => `- ${m.name} ${m.dose} ${m.route} ${m.frequency}`),
        ``,
        `### Evoluções (últimas)`,
        ...d.notes.slice(-2).map((n) => `- [${n.type}] ${n.text.replace(/\b(Dr\.|Dra\.|Enf\.)\s+[A-ZÀ-Ú][\wÀ-ú]+(\s+[A-ZÀ-Ú][\wÀ-ú]+)*/g, "[PROFISSIONAL]")}`),
      ].join("\n");
      return { anonymized_context: txt, pii_redacted: 3 };
    },
  },
  assistant: {
    async chat(req): Promise<ChatResponse> {
      await latency(900, 1800);
      const built = buildAnswer(req);
      return persistChat(req, built, built.blocked ? 210 : 1400 + Math.round(Math.random() * 1500));
    },
    async stream(req, onEvent, signal) {
      const start = Date.now();
      const built = buildAnswer(req);
      const emit = (ev: StreamEvent) => {
        if (signal?.aborted) throw new DOMException("Aborted", "AbortError");
        onEvent(ev);
      };
      const convId = req.conversation_id ?? uid("conv");
      const messageId = state.nextMsgId + 1;
      emit({ event: "meta", data: { conversation_id: convId, message_id: messageId, trace_id: uid("trc"), intent: built.intent, patient_id: req.patient_id ?? null } });
      await sleep(150);
      emit({ event: "step", data: { node: "guard_input", label: "Guardrail de entrada", status: built.blocked ? "erro" : "ok" } });
      if (built.blocked) {
        await sleep(120);
        emit({ event: "guardrail", data: built.guardrail });
        for (const w of built.answer.split(/(\s+)/)) {
          emit({ event: "token", data: { delta: w } });
          await sleep(8);
        }
        const resp = persistChat(req, built, Date.now() - start);
        emit({ event: "done", data: resp });
        return;
      }
      await sleep(180);
      emit({ event: "step", data: { node: "classify", label: "Classificar intenção", status: "ok" } });
      await sleep(260);
      emit({ event: "step", data: { node: "retrieve", label: "RAG + contexto", status: "ok" } });
      emit({ event: "citations", data: { citations: built.citations } });
      await sleep(200);
      emit({ event: "step", data: { node: "generate", label: "LLM fine-tunada", status: "executando" } });
      const tokens = built.answer.match(/\S+\s*|\s+/g) ?? [built.answer];
      for (const t of tokens) {
        emit({ event: "token", data: { delta: t } });
        await sleep(14 + Math.random() * 26);
      }
      emit({ event: "step", data: { node: "generate", label: "LLM fine-tunada", status: "ok" } });
      await sleep(150);
      emit({ event: "guardrail", data: built.guardrail });
      emit({ event: "step", data: { node: "guard_output", label: "Guardrail de saída", status: "ok" } });
      const resp = persistChat({ ...req, conversation_id: req.conversation_id ?? null }, built, Date.now() - start);
      emit({ event: "done", data: resp });
    },
    async conversations(): Promise<Conversation[]> {
      await latency();
      return [...state.conversations].sort((a, b) => b.updated_at.localeCompare(a.updated_at));
    },
    async conversation(id): Promise<ConversationDetail> {
      await latency();
      const c = state.conversations.find((x) => x.id === id);
      if (!c) throw new MockApiError(404, "Conversa não encontrada");
      return { ...c, messages: state.messages[id] ?? [] };
    },
    async deleteConversation(id) {
      await latency();
      state.conversations = state.conversations.filter((c) => c.id !== id);
      delete state.messages[id];
      return { ok: true as const };
    },
    async feedback(req: FeedbackRequest) {
      await latency(80, 200);
      for (const msgs of Object.values(state.messages)) {
        const m = msgs.find((x) => x.id === req.message_id);
        if (m) m.feedback = req.rating;
      }
      return { ok: true as const };
    },
    async suggestions(patientId) {
      await latency(80, 200);
      const p = patientId ? PATIENTS.find((x) => x.id === patientId) : null;
      return { suggestions: p ? SUGGESTIONS_PATIENT(p.name) : SUGGESTIONS_GENERIC };
    },
    async graph() {
      await latency();
      requirePerm("system:internals");
      return { mermaid: CHAT_GRAPH_MERMAID };
    },
  },
  workflows: {
    async clinicalReview(patient_id, reason): Promise<WorkflowRun> {
      await latency(1200, 2200);
      const p = PATIENTS.find((x) => x.id === patient_id);
      if (!p) throw new MockApiError(404, "Paciente não encontrado");
      const template = state.runs.find((r) => r.patient_id === patient_id) ?? state.runs[0];
      const run_id = uid("run");
      const now = new Date().toISOString();
      const u = currentUser();
      const newRun: WorkflowRun = {
        ...template,
        run_id,
        patient_id: p.id,
        patient_name: p.name,
        status: "aguardando_aprovacao",
        reason: reason ?? null,
        started_by: u.name,
        started_at: now,
        finished_at: null,
        human_decision: null,
        trace_id: uid("trc"),
        steps: template.steps.filter((s) => s.node !== "finalize").map((s, i) => ({ ...s, started_at: new Date(Date.now() + i * 400).toISOString(), ...(s.node === "human_review" ? { status: "aguardando" as const, summary: "Grafo interrompido aguardando decisão de médico/admin.", data: null, duration_ms: 0 } : {}) })),
        result: template.result ? { ...template.result, risk_level: p.risk_level } : null,
      };
      state.runs.unshift(newRun);
      return newRun;
    },
    async decision(run_id, approved, comment): Promise<WorkflowRun> {
      await latency(500, 900);
      const u = currentUser();
      if (u.role !== "medico" && u.role !== "admin") throw new MockApiError(403, "Apenas médicos ou administradores podem decidir");
      const run = state.runs.find((r) => r.run_id === run_id);
      if (!run) throw new MockApiError(404, "Execução não encontrada");
      if (run.status !== "aguardando_aprovacao") throw new MockApiError(409, "Execução não está aguardando aprovação");
      const decided_at = new Date().toISOString();
      run.status = approved ? "aprovado" : "rejeitado";
      run.finished_at = decided_at;
      run.human_decision = { approved, comment: comment || null, decided_by: u.name, decided_at };
      run.steps = run.steps.map((s) => (s.node === "human_review" ? { ...s, status: "ok", duration_ms: Date.now() - new Date(s.started_at).getTime(), summary: `${approved ? "Aprovado" : "Rejeitado"} por ${u.name}.`, data: { ...run.human_decision } } : s));
      run.steps.push({ node: "finalize", label: "Registrar decisão", status: "ok", started_at: decided_at, duration_ms: 21, summary: "Decisão registrada na trilha de auditoria.", data: { audit_action: "workflow.decision" } });
      return { ...run };
    },
    async runs(params): Promise<WorkflowRun[]> {
      await latency();
      let list = [...state.runs].sort((a, b) => b.started_at.localeCompare(a.started_at));
      if (params?.patient_id) list = list.filter((r) => r.patient_id === params.patient_id);
      if (params?.status) list = list.filter((r) => r.status === params.status);
      if (params?.limit) list = list.slice(0, params.limit);
      return list;
    },
    async run(run_id): Promise<WorkflowRun> {
      await latency(80, 250);
      const r = state.runs.find((x) => x.run_id === run_id);
      if (!r) throw new MockApiError(404, "Execução não encontrada");
      return { ...r };
    },
    async graph(): Promise<WorkflowGraph> {
      await latency();
      requirePerm("system:internals");
      return WORKFLOW_GRAPH;
    },
  },
  alerts: {
    async list(params): Promise<Alert[]> {
      await latency();
      let list = [...state.alerts].sort((a, b) => b.created_at.localeCompare(a.created_at));
      if (params?.patient_id) list = list.filter((a) => a.patient_id === params.patient_id);
      if (params?.severity) list = list.filter((a) => a.severity === params.severity);
      if (params?.open_only) list = list.filter((a) => !a.acknowledged_at);
      return list;
    },
    async ack(id): Promise<Alert> {
      await latency(200, 400);
      const a = state.alerts.find((x) => x.id === id);
      if (!a) throw new MockApiError(404, "Alerta não encontrado");
      a.acknowledged_at = new Date().toISOString();
      a.acknowledged_by = currentUser().name;
      return { ...a };
    },
  },
  knowledge: {
    async documents(doc_type): Promise<KnowledgeDocument[]> {
      await latency();
      return doc_type ? KNOWLEDGE_DOCS.filter((d) => d.doc_type === doc_type) : KNOWLEDGE_DOCS;
    },
    async document(id): Promise<KnowledgeDocumentDetail> {
      await latency();
      const d = knowledgeDetail(id);
      if (!d) throw new MockApiError(404, "Documento não encontrado");
      return d;
    },
    async search(query, k = 5, doc_type): Promise<KnowledgeSearchResponse> {
      await latency(300, 700);
      const q = query.toLowerCase();
      const words = q.split(/\W+/).filter((w) => w.length > 3);
      const scored = CITATIONS.filter((c) => !doc_type || c.doc_type === doc_type)
        .map((c) => {
          const hay = `${c.title} ${c.section ?? ""} ${c.chunk}`.toLowerCase();
          const hits = words.filter((w) => hay.includes(w)).length;
          return { ...c, score: Math.min(0.98, Math.max(0.21, (hits / Math.max(1, words.length)) * 0.7 + c.score * 0.3)) };
        })
        .sort((a, b) => b.score - a.score)
        .slice(0, k)
        .map((c, i) => ({ ...c, id: i + 1 }));
      return { results: scored, latency_ms: 240 + Math.round(Math.random() * 200) };
    },
    async reindex(): Promise<ReindexResponse> {
      await latency(1500, 2500);
      requirePerm("knowledge:manage", "Apenas administradores podem reindexar");
      return { documents: KNOWLEDGE_DOCS.length, chunks: KNOWLEDGE_DOCS.reduce((s, d) => s + d.chunks, 0), duration_ms: 18400 };
    },
  },
  model: {
    async info(): Promise<ModelInfoResponse> {
      await latency();
      return { ...state.model };
    },
    async switch(model) {
      await latency(400, 800);
      requirePerm("model:read", "Apenas administradores podem trocar o modelo");
      const m = state.model.available.find((x) => x.name === model);
      if (!m) throw new MockApiError(404, "Modelo não disponível");
      state.model.active = { provider: "ollama", name: m.name, fine_tuned: m.fine_tuned, base_model: m.fine_tuned ? "llama3.1:8b" : null };
      return { active: state.model.active };
    },
  },
  audit: {
    async list(params): Promise<AuditListResponse> {
      await latency();
      let list = AUDIT;
      if (params?.action) list = list.filter((a) => a.action === params.action);
      if (params?.user_id) list = list.filter((a) => a.user_id === params.user_id);
      if (params?.q) {
        const q = params.q.toLowerCase();
        list = list.filter((a) => [a.user_name, a.action, a.resource_type, a.resource_id, a.trace_id, a.ip, JSON.stringify(a.details)].some((v) => v?.toLowerCase().includes(q)));
      }
      const offset = params?.offset ?? 0;
      const limit = params?.limit ?? 50;
      return { items: list.slice(offset, offset + limit), total: list.length };
    },
    async get(id): Promise<AuditEntry> {
      await latency();
      const a = AUDIT.find((x) => x.id === id);
      if (!a) throw new MockApiError(404, "Registro não encontrado");
      return a;
    },
    async verify(): Promise<AuditVerifyResponse> {
      await latency(800, 1500);
      return { ok: true, checked: AUDIT.length, broken_at: null };
    },
    async actions(): Promise<string[]> {
      await latency(50, 150);
      return AUDIT_ACTIONS;
    },
  },
};

/** Aplica a regra 428 (como o backend) a todas as rotas exceto /auth/* e /health. */
function guardNamespace<T extends object>(ns: T): T {
  const out: Record<string, unknown> = {};
  for (const [k, fn] of Object.entries(ns as Record<string, unknown>)) {
    out[k] =
      typeof fn === "function"
        ? async (...args: unknown[]) => {
            assertPrecondition();
            return (fn as (...a: unknown[]) => unknown)(...args);
          }
        : fn;
  }
  return out as T;
}

export const mockApi: ApiClient = {
  health: rawMockApi.health,
  publicConfig: rawMockApi.publicConfig,
  auth: rawMockApi.auth,
  users: guardNamespace(rawMockApi.users),
  docsHub: { ...guardNamespace(rawMockApi.docsHub), downloadUrl: rawMockApi.docsHub.downloadUrl },
  catalog: guardNamespace(rawMockApi.catalog),
  dashboard: guardNamespace(rawMockApi.dashboard),
  patients: guardNamespace(rawMockApi.patients),
  assistant: guardNamespace(rawMockApi.assistant),
  workflows: guardNamespace(rawMockApi.workflows),
  alerts: guardNamespace(rawMockApi.alerts),
  knowledge: guardNamespace(rawMockApi.knowledge),
  model: guardNamespace(rawMockApi.model),
  audit: guardNamespace(rawMockApi.audit),
};
