// Implementação MOCK do cliente de API — mesmos contratos, dados locais (lib/mock/data.ts)
import type {
  Alert, AuditEntry, AuditListResponse, AuditVerifyResponse, ChatMessage, ChatRequest, ChatResponse, Conversation,
  ConversationDetail, DashboardStats, Exam, FeedbackRequest, HealthResponse, KnowledgeDocument, KnowledgeDocumentDetail,
  KnowledgeSearchResponse, LoginResponse, ModelInfoResponse, Patient, PatientContext, PatientDetail, ReindexResponse,
  StreamEvent, User, WorkflowGraph, WorkflowRun, Guardrail, Citation, Intent,
} from "@/lib/types";
import type { ApiClient, ApiError as ApiErrorT } from "@/lib/api-types";
import {
  ALERTS, AUDIT, AUDIT_ACTIONS, CHAT_GRAPH_MERMAID, CITATIONS, CONVERSATIONS, CONV_MESSAGES, KNOWLEDGE_DOCS, MODEL_ACTIVE, MODEL_INFO,
  PATIENTS, PATIENT_DETAILS, RUNS, SUGGESTIONS_GENERIC, SUGGESTIONS_PATIENT, USERS, WORKFLOW_GRAPH, citationsFor, knowledgeDetail,
} from "./data";
import { sleep, uid } from "@/lib/utils";

class MockApiError extends Error implements ApiErrorT {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
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
};

const latency = (min = 120, max = 420) => sleep(min + Math.random() * (max - min));

function currentUser(): User {
  if (state.currentUser) return state.currentUser;
  if (typeof window !== "undefined") {
    try {
      const raw = localStorage.getItem("asclepio.user");
      if (raw) return (state.currentUser = JSON.parse(raw) as User);
    } catch {
      /* ignore */
    }
  }
  return USERS[1];
}

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

export const mockApi: ApiClient = {
  async health(): Promise<HealthResponse> {
    await latency();
    return { status: "ok", version: "0.3.0-mock", env: "mock", llm: { provider: "ollama", model: state.model.active.name, reachable: true }, embeddings: { provider: "ollama", model: "nomic-embed-text" }, db: "ok", vectorstore: { chunks: 156 } };
  },
  auth: {
    async login(email, password): Promise<LoginResponse> {
      await latency(300, 700);
      const u = USERS.find((x) => x.email.toLowerCase() === email.trim().toLowerCase());
      if (!u || u.password !== password) throw new MockApiError(401, "E-mail ou senha inválidos");
      const { password: _pw, ...user } = u;
      void _pw;
      state.currentUser = user;
      return { access_token: `mock.${btoa(user.email)}.${Date.now()}`, token_type: "bearer", expires_in: 28800, user };
    },
    async me(): Promise<User> {
      await latency(50, 150);
      return currentUser();
    },
    async logout() {
      await latency(50, 150);
      state.currentUser = null;
      return { ok: true as const };
    },
  },
  dashboard: {
    async stats(): Promise<DashboardStats> {
      await latency();
      const dist = { baixo: 0, moderado: 0, alto: 0, critico: 0 };
      PATIENTS.forEach((p) => dist[p.risk_level]++);
      return {
        patients: PATIENTS.length,
        patients_critical: dist.critico,
        pending_exams: PATIENTS.reduce((s, p) => s + p.pending_exams_count, 0),
        overdue_exams: PATIENTS.reduce((s, p) => s + p.overdue_exams_count, 0),
        open_alerts: state.alerts.filter((a) => !a.acknowledged_at).length,
        chats_today: 14,
        workflows_today: state.runs.length,
        guardrail_blocks_today: 2,
        model: state.model.active,
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
      if (currentUser().role !== "admin") throw new MockApiError(403, "Apenas administradores podem reindexar");
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
      if (currentUser().role !== "admin") throw new MockApiError(403, "Apenas administradores podem trocar o modelo");
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
