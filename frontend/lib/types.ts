// Tipos do contrato da API — docs/CONTRATO_API.md (v1 + auth v1.1)

export type Role = "admin" | "medico" | "enfermagem" | "auditor";
export type User = {
  id: number;
  name: string;
  email: string;
  role: Role;
  crm: string | null;
  specialty: string | null;
  avatar_initials: string;
  specialty_id: number | null;
  sector_id: number | null;
  permissions: string[];
  mfa_enabled: boolean;
  must_change_password: boolean;
  is_active: boolean;
  is_demo: boolean;
  last_login_at: string | null;
  created_at: string;
};

export type RiskLevel = "baixo" | "moderado" | "alto" | "critico";
export type Patient = {
  id: number;
  mrn: string;
  name: string;
  birth_date: string;
  age: number;
  sex: "F" | "M";
  ward: string;
  bed: string;
  admission_date: string;
  primary_diagnosis: string;
  risk_level: RiskLevel;
  pending_exams_count: number;
  overdue_exams_count: number;
  active_alerts_count: number;
};
export type Vital = {
  measured_at: string;
  hr: number;
  sbp: number;
  dbp: number;
  rr: number;
  temp_c: number;
  spo2: number;
  gcs: number | null;
};
export type ExamStatus = "pendente" | "coletado" | "concluido" | "atrasado";
export type ExamCategory = "laboratorio" | "imagem" | "cardiologia" | "outros";
export type Exam = {
  id: number;
  name: string;
  category: ExamCategory;
  status: ExamStatus;
  requested_at: string;
  due_at: string | null;
  result_at: string | null;
  result_value: string | null;
  unit: string | null;
  reference_range: string | null;
  is_critical: boolean;
  note: string | null;
};
export type Medication = {
  id: number;
  name: string;
  dose: string;
  route: string;
  frequency: string;
  started_at: string;
  status: "ativo" | "suspenso";
};
export type ClinicalNote = {
  id: number;
  created_at: string;
  author: string;
  type: "admissao" | "evolucao" | "prescricao" | "parecer";
  text: string;
};
export type AlertSeverity = "info" | "atencao" | "critico";
export type Alert = {
  id: number;
  patient_id: number;
  patient_name: string;
  severity: AlertSeverity;
  title: string;
  message: string;
  source: "fluxo" | "regra" | "manual";
  run_id: string | null;
  created_at: string;
  acknowledged_at: string | null;
  acknowledged_by: string | null;
};
export type PatientDetail = Patient & {
  allergies: string[];
  comorbidities: string[];
  weight_kg: number;
  height_cm: number;
  blood_type: string;
  vitals: Vital[];
  exams: Exam[];
  medications: Medication[];
  notes: ClinicalNote[];
  alerts: Alert[];
};

export type DocType = "protocolo" | "faq" | "modelo" | "prontuario";
export type Citation = {
  id: number;
  source_id: string;
  title: string;
  section: string | null;
  doc_type: DocType;
  chunk: string;
  score: number;
  path: string | null;
};
export type GuardrailStatus = "aprovado" | "ajustado" | "bloqueado";
export type Guardrail = {
  status: GuardrailStatus;
  flags: string[];
  notes: string[];
  pii_redacted: number;
  injection_detected: boolean;
};
export type Intent = "protocolo" | "paciente" | "documento" | "geral" | "prescricao" | "fora_escopo";
export type ModelInfo = {
  provider: "ollama" | "openai" | "fake";
  name: string;
  fine_tuned: boolean;
  base_model: string | null;
};
export type Confidence = "alta" | "media" | "baixa";
export type ChatResponse = {
  conversation_id: string;
  message_id: number;
  answer: string;
  citations: Citation[];
  guardrail: Guardrail;
  intent: Intent;
  model: ModelInfo;
  latency_ms: number;
  trace_id: string;
  confidence: Confidence;
  patient_id: number | null;
};
export type ChatMessage = {
  id: number;
  role: "user" | "assistant";
  content: string;
  created_at: string;
  citations: Citation[];
  guardrail: Guardrail | null;
  intent: Intent | null;
  latency_ms: number | null;
  feedback: 1 | -1 | null;
};
export type Conversation = {
  id: string;
  title: string;
  patient_id: number | null;
  patient_name: string | null;
  created_at: string;
  updated_at: string;
  message_count: number;
};
export type ConversationDetail = Conversation & { messages: ChatMessage[] };

export type StepStatus = "ok" | "alerta" | "erro" | "pulado" | "aguardando";
export type WorkflowStep = {
  node: string;
  label: string;
  status: StepStatus;
  started_at: string;
  duration_ms: number;
  summary: string;
  data: Record<string, unknown> | null;
};
export type SuggestionPriority = "alta" | "media" | "baixa";
export type SuggestionCategory = "exame" | "conduta" | "monitorizacao" | "alerta" | "encaminhamento";
export type Suggestion = {
  title: string;
  rationale: string;
  priority: SuggestionPriority;
  category: SuggestionCategory;
  citations: Citation[];
};
export type RunStatus = "executando" | "aguardando_aprovacao" | "aprovado" | "rejeitado" | "erro";
export type WorkflowResult = {
  risk_level: RiskLevel;
  risk_score: number;
  risk_factors: string[];
  pending_exams: Exam[];
  critical_values: { exam: string; value: string; rule: string }[];
  suggestions: Suggestion[];
  alerts: Alert[];
  llm_summary: string;
  guardrail: Guardrail;
  citations: Citation[];
};
export type HumanDecision = {
  approved: boolean;
  comment: string | null;
  decided_by: string;
  decided_at: string;
};
export type WorkflowRun = {
  run_id: string;
  patient_id: number;
  patient_name: string;
  status: RunStatus;
  reason: string | null;
  started_by: string;
  started_at: string;
  finished_at: string | null;
  steps: WorkflowStep[];
  result: WorkflowResult | null;
  human_decision: HumanDecision | null;
  trace_id: string;
  model: ModelInfo;
};

export type AuditEntry = {
  id: number;
  created_at: string;
  user_id: number | null;
  user_name: string | null;
  user_role: Role | null;
  action: string;
  resource_type: string | null;
  resource_id: string | null;
  trace_id: string | null;
  ip: string | null;
  details: Record<string, unknown>;
  prev_hash: string;
  hash: string;
};
export type KnowledgeDocument = {
  id: string;
  title: string;
  doc_type: DocType;
  path: string;
  version: string | null;
  category: string | null;
  tags: string[];
  chunks: number;
  updated_at: string | null;
  size_chars: number;
};
export type KnowledgeDocumentDetail = KnowledgeDocument & { content: string };

// ---- Respostas compostas ----
/** Resposta de login/refresh/mfa-verify (contrato v1.1). */
export type TokenOut = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
  refresh_expires_in: number;
  user: User;
  must_change_password: boolean;
};
/** Resposta de login quando o usuário tem MFA ativo (HTTP 200). */
export type MfaChallenge = {
  mfa_required: true;
  mfa_token: string;
  expires_in: number;
  methods: ("totp" | "recovery_code")[];
};
export type LoginResponse = TokenOut | MfaChallenge;
export function isMfaChallenge(r: LoginResponse): r is MfaChallenge {
  return (r as MfaChallenge).mfa_required === true;
}
export type Session = {
  id: number;
  created_at: string;
  last_used_at: string | null;
  expires_at: string;
  ip: string | null;
  user_agent: string | null;
  current: boolean;
};
export type MfaSetup = { secret: string; otpauth_uri: string; qr_svg: string };
export type MfaEnableResponse = { ok: true; recovery_codes: string[] };

// ---- Gestão de usuários (admin) ----
export type UserCreateInput = { name: string; email: string; role: Role; crm?: string | null; specialty?: string | null; specialty_id?: number | null; sector_id?: number | null; password?: string };
export type UserUpdateInput = { name?: string; role?: Role; crm?: string | null; specialty?: string | null; specialty_id?: number | null; sector_id?: number | null; is_active?: boolean };
export type UserCreateResponse = { user: User; temporary_password: string | null };
export type UsersListParams = { role?: Role | ""; active?: boolean | ""; q?: string };

// ---- Plataforma (v1.2): configuração pública e catálogos ----
export type PublicConfig = {
  app_name: string;
  hospital_name: string;
  hospital_short_name: string;
  version: string;
  demo_mode: boolean;
  mfa_required_roles: string[];
  support_email: string | null;
};
export type Specialty = { id: number; name: string; code: string | null; active: boolean; professionals_count: number };
export type SectorKind = "pronto_socorro" | "internacao" | "uti" | "ambulatorio" | "cirurgico" | "outro";
export type Sector = { id: number; name: string; kind: SectorKind; active: boolean; patients_count: number };
export type SpecialtyInput = { name?: string; code?: string | null; active?: boolean };
export type SectorInput = { name?: string; kind?: SectorKind; active?: boolean };

// ---- Central de documentação (v1.3) ----
export type DocFormat = "md" | "pdf" | "mmd";
export type HubDocument = {
  id: string;
  title: string;
  description: string;
  format: DocFormat;
  filename: string;
  size_bytes: number;
  updated_at: string | null;
  readable: boolean;
  downloadable: boolean;
};
export type HubCategory = { id: string; title: string; description: string; documents: HubDocument[] };
export type DocsHubList = { categories: HubCategory[]; total: number };
export type HubDocumentContent = HubDocument & { content: string };

export type DashboardStats = {
  patients: number;
  patients_critical: number;
  pending_exams: number;
  overdue_exams: number;
  open_alerts: number;
  chats_today: number;
  workflows_today: number;
  /** null para quem não tem `audit:read` */
  guardrail_blocks_today: number | null;
  /** null para quem não tem `model:read` */
  model: ModelInfo | null;
  /** status do sistema (admin) — null para os demais */
  system: HealthResponse | null;
  /** bloco "Meu trabalho" (medico/enfermagem) — null para os demais */
  my_work: MyWork | null;
  recent_alerts: Alert[];
  recent_runs: WorkflowRun[];
  risk_distribution: Record<RiskLevel, number>;
};
export type MyWork = { pending_approvals: WorkflowRun[]; my_open_alerts: number; my_conversations_today: number };

export type PatientContext = { anonymized_context: string; pii_redacted: number };

export type ChatRequest = { message: string; patient_id?: number | null; conversation_id?: string | null };
export type FeedbackRequest = { message_id: number; rating: 1 | -1; comment?: string };

export type WorkflowGraph = { mermaid: string; nodes: { id: string; label: string; description: string }[] };

export type KnowledgeSearchResponse = { results: Citation[]; latency_ms: number };
export type ReindexResponse = { documents: number; chunks: number; duration_ms: number };

export type FinetuneMeta = {
  run_id: string;
  base_model: string;
  method: string;
  trained_at: string;
  epochs: number;
  train_examples: number;
  eval_examples: number;
  final_train_loss: number;
  final_eval_loss: number;
  lora_r: number;
  lora_alpha: number;
  learning_rate: number;
  duration_min: number;
  device: string;
  ollama_model: string;
};
export type EvalModelMetrics = {
  rouge_l: number;
  bleu: number;
  keyword_coverage: number;
  judge_score: number;
  guardrail_compliance: number;
  avg_latency_ms: number;
  n: number;
};
export type EvalSample = {
  id: string | number;
  category?: string | null;
  question: string;
  reference?: string | null;
  outputs: Record<string, { answer: string; rouge_l?: number; keyword_coverage?: number; judge_score?: number; latency_ms?: number }>;
  [key: string]: unknown;
};
export type EvalReport = {
  generated_at: string;
  models: Record<string, EvalModelMetrics>;
  rag: { hit_rate_at_5: number; mrr: number };
  per_sample: EvalSample[];
};
export type ModelInfoResponse = {
  active: ModelInfo;
  available: { name: string; fine_tuned: boolean; size: string }[];
  finetune: FinetuneMeta | null;
  evaluation: EvalReport | null;
  embeddings: { provider: string; model: string };
};

export type AuditListResponse = { items: AuditEntry[]; total: number };
export type AuditVerifyResponse = { ok: boolean; checked: number; broken_at: number | null };

export type HealthResponse = {
  status: "ok" | "degraded";
  version: string;
  env: string;
  llm: { provider: string; model: string; reachable: boolean };
  embeddings: Record<string, unknown>;
  db: string;
  vectorstore: { chunks: number };
};

// ---- SSE ----
export type SseMeta = { conversation_id: string; message_id: number; trace_id: string; intent: Intent; patient_id: number | null };
export type SseStep = { node: string; label: string; status: StepStatus | "ok" | "executando" };
export type StreamEvent =
  | { event: "meta"; data: SseMeta }
  | { event: "step"; data: SseStep }
  | { event: "token"; data: { delta: string } }
  | { event: "citations"; data: { citations: Citation[] } }
  | { event: "guardrail"; data: Guardrail }
  | { event: "done"; data: ChatResponse }
  | { event: "error"; data: { detail: string } };
