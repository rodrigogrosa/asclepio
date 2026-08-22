# Contrato da API — Asclépio (v1)

Base URL: `http://localhost:8000/api/v1` · Docs interativas: `/docs` (Swagger) e `/redoc`.
Autenticação: `Authorization: Bearer <jwt>` (obtido em `POST /auth/login`). Todas as rotas exceto `/auth/login`, `/health` e `/metrics` exigem token.
Erros: `{"detail": "mensagem"}` com status HTTP adequado (400/401/403/404/409/422/429/500). Toda resposta carrega header `X-Request-ID` (trace_id).

## Papéis (RBAC)
`admin` (tudo), `medico` (pacientes, assistente, fluxos, aprovar fluxos), `enfermagem` (pacientes, assistente, fluxos sem aprovação, ack de alertas), `auditor` (somente leitura de auditoria, dashboard, modelo).

Usuários seed (senha de todos: `Asclepio@2026`):
| email | papel | nome |
|---|---|---|
| admin@asclepio.fiap | admin | Administrador do Sistema |
| dra.ana@asclepio.fiap | medico | Dra. Ana Beatriz Souza (CRM 123456-SP · Clínica Médica) |
| dr.marcos@asclepio.fiap | medico | Dr. Marcos Vinícius Lima (CRM 654321-SP · Emergência) |
| enf.carla@asclepio.fiap | enfermagem | Enf. Carla Mendes (COREN 98765-SP) |
| auditor@asclepio.fiap | auditor | Auditoria Clínica |

## Tipos (JSON)
```ts
type Role = "admin" | "medico" | "enfermagem" | "auditor";
type User = { id: number; name: string; email: string; role: Role; crm: string | null; specialty: string | null; avatar_initials: string };

type RiskLevel = "baixo" | "moderado" | "alto" | "critico";
type Patient = { id: number; mrn: string; name: string; birth_date: string; age: number; sex: "F" | "M";
  ward: string; bed: string; admission_date: string; primary_diagnosis: string; risk_level: RiskLevel;
  pending_exams_count: number; overdue_exams_count: number; active_alerts_count: number };
type Vital = { measured_at: string; hr: number; sbp: number; dbp: number; rr: number; temp_c: number; spo2: number; gcs: number | null };
type ExamStatus = "pendente" | "coletado" | "concluido" | "atrasado";
type Exam = { id: number; name: string; category: "laboratorio" | "imagem" | "cardiologia" | "outros"; status: ExamStatus;
  requested_at: string; due_at: string | null; result_at: string | null; result_value: string | null; unit: string | null;
  reference_range: string | null; is_critical: boolean; note: string | null };
type Medication = { id: number; name: string; dose: string; route: string; frequency: string; started_at: string; status: "ativo" | "suspenso" };
type ClinicalNote = { id: number; created_at: string; author: string; type: "admissao" | "evolucao" | "prescricao" | "parecer"; text: string };
type Alert = { id: number; patient_id: number; patient_name: string; severity: "info" | "atencao" | "critico"; title: string; message: string;
  source: "fluxo" | "regra" | "manual"; run_id: string | null; created_at: string; acknowledged_at: string | null; acknowledged_by: string | null };
type PatientDetail = Patient & { allergies: string[]; comorbidities: string[]; weight_kg: number; height_cm: number; blood_type: string;
  vitals: Vital[]; exams: Exam[]; medications: Medication[]; notes: ClinicalNote[]; alerts: Alert[] };

type DocType = "protocolo" | "faq" | "modelo" | "prontuario";
type Citation = { id: number; source_id: string; title: string; section: string | null; doc_type: DocType; chunk: string; score: number; path: string | null };
type GuardrailStatus = "aprovado" | "ajustado" | "bloqueado";
type Guardrail = { status: GuardrailStatus; flags: string[]; notes: string[]; pii_redacted: number; injection_detected: boolean };
type Intent = "protocolo" | "paciente" | "documento" | "geral" | "prescricao" | "fora_escopo";
type ModelInfo = { provider: "ollama" | "openai" | "fake"; name: string; fine_tuned: boolean; base_model: string | null };
type ChatResponse = { conversation_id: string; message_id: number; answer: string; citations: Citation[]; guardrail: Guardrail;
  intent: Intent; model: ModelInfo; latency_ms: number; trace_id: string; confidence: "alta" | "media" | "baixa"; patient_id: number | null };
type ChatMessage = { id: number; role: "user" | "assistant"; content: string; created_at: string; citations: Citation[]; guardrail: Guardrail | null;
  intent: Intent | null; latency_ms: number | null; feedback: 1 | -1 | null };
type Conversation = { id: string; title: string; patient_id: number | null; patient_name: string | null; created_at: string; updated_at: string; message_count: number };

type StepStatus = "ok" | "alerta" | "erro" | "pulado" | "aguardando";
type WorkflowStep = { node: string; label: string; status: StepStatus; started_at: string; duration_ms: number; summary: string; data: Record<string, unknown> | null };
type Suggestion = { title: string; rationale: string; priority: "alta" | "media" | "baixa"; category: "exame" | "conduta" | "monitorizacao" | "alerta" | "encaminhamento"; citations: Citation[] };
type RunStatus = "executando" | "aguardando_aprovacao" | "aprovado" | "rejeitado" | "erro";
type WorkflowResult = { risk_level: RiskLevel; risk_score: number; risk_factors: string[]; pending_exams: Exam[]; critical_values: { exam: string; value: string; rule: string }[];
  suggestions: Suggestion[]; alerts: Alert[]; llm_summary: string; guardrail: Guardrail; citations: Citation[] };
type WorkflowRun = { run_id: string; patient_id: number; patient_name: string; status: RunStatus; reason: string | null; started_by: string;
  started_at: string; finished_at: string | null; steps: WorkflowStep[]; result: WorkflowResult | null;
  human_decision: { approved: boolean; comment: string | null; decided_by: string; decided_at: string } | null; trace_id: string; model: ModelInfo };

type AuditEntry = { id: number; created_at: string; user_id: number | null; user_name: string | null; user_role: Role | null; action: string;
  resource_type: string | null; resource_id: string | null; trace_id: string | null; ip: string | null; details: Record<string, unknown>; prev_hash: string; hash: string };
type KnowledgeDocument = { id: string; title: string; doc_type: DocType; path: string; version: string | null; category: string | null; tags: string[]; chunks: number; updated_at: string | null; size_chars: number };
```

## Endpoints
### Auth
- `POST /auth/login` `{email, password}` → `{access_token, token_type:"bearer", expires_in, user: User}` · 401 se inválido · rate-limited (10/min).
- `GET /auth/me` → `User`
- `POST /auth/logout` → `{ok:true}` (registra auditoria; token é stateless)

### Dashboard
- `GET /dashboard/stats` → `{patients, patients_critical, pending_exams, overdue_exams, open_alerts, chats_today, workflows_today, guardrail_blocks_today, model: ModelInfo, recent_alerts: Alert[], recent_runs: WorkflowRun[] (sem steps), risk_distribution: {baixo,moderado,alto,critico}}`

### Pacientes
- `GET /patients?search=&ward=&risk=` → `Patient[]`
- `GET /patients/{id}` → `PatientDetail`
- `GET /patients/{id}/pending-exams` → `Exam[]`
- `GET /patients/{id}/context` → `{anonymized_context: string, pii_redacted: number}` (exatamente o texto que a LLM recebe — explainability)

### Assistente (LangChain / LangGraph)
- `POST /assistant/chat` `{message, patient_id?, conversation_id?}` → `ChatResponse`
- `POST /assistant/chat/stream` mesmo corpo → **SSE** (`text/event-stream`). Eventos, cada um `event: <nome>\ndata: <json>\n\n`:
  - `meta` `{conversation_id, message_id, trace_id, intent, patient_id}`
  - `step` `{node, label, status}` (progresso do grafo: guard_input → classify → retrieve → generate → guard_output)
  - `token` `{delta}`
  - `citations` `{citations: Citation[]}`
  - `guardrail` `Guardrail`
  - `done` `ChatResponse`
  - `error` `{detail}`
- `GET /assistant/conversations` → `Conversation[]` (do usuário logado; admin vê todas)
- `GET /assistant/conversations/{id}` → `Conversation & {messages: ChatMessage[]}`
- `DELETE /assistant/conversations/{id}` → `{ok:true}`
- `POST /assistant/feedback` `{message_id, rating: 1|-1, comment?}` → `{ok:true}`
- `GET /assistant/suggestions?patient_id=` → `{suggestions: string[]}` (perguntas de exemplo)
- `GET /assistant/graph` → `{mermaid: string}` (grafo do chat)

### Fluxos clínicos (LangGraph)
- `POST /workflows/clinical-review` `{patient_id, reason?}` → `WorkflowRun` (executa até o nó `human_review` e retorna `status:"aguardando_aprovacao"`; se risco crítico, alertas já são emitidos antes da pausa)
- `POST /workflows/runs/{run_id}/decision` `{approved: boolean, comment?}` → `WorkflowRun` (retoma o grafo; só `medico`/`admin`)
- `GET /workflows/runs?patient_id=&status=&limit=` → `WorkflowRun[]`
- `GET /workflows/runs/{run_id}` → `WorkflowRun`
- `GET /workflows/graph` → `{mermaid: string, nodes: {id,label,description}[]}`

### Alertas
- `GET /alerts?patient_id=&severity=&open_only=true` → `Alert[]`
- `POST /alerts/{id}/ack` → `Alert`

### Base de conhecimento (RAG)
- `GET /knowledge/documents?doc_type=` → `KnowledgeDocument[]`
- `GET /knowledge/documents/{id}` → `KnowledgeDocument & {content: string}`
- `POST /knowledge/search` `{query, k?, doc_type?}` → `{results: Citation[], latency_ms}`
- `POST /knowledge/reindex` (admin) → `{documents, chunks, duration_ms}`

### Modelo
- `GET /model/info` → `{active: ModelInfo, available: {name, fine_tuned, size}[], finetune: FinetuneMeta|null, evaluation: EvalReport|null, embeddings: {provider, model}}`
  - `FinetuneMeta = {run_id, base_model, method, trained_at, epochs, train_examples, eval_examples, final_train_loss, final_eval_loss, lora_r, lora_alpha, learning_rate, duration_min, device, ollama_model}`
  - `EvalReport` = conteúdo de `ml/reports/eval_latest.json` (ver `ml/README.md`): `{generated_at, models: {name: {rouge_l, bleu, keyword_coverage, judge_score, guardrail_compliance, avg_latency_ms, n}}, rag: {hit_rate_at_5, mrr}, per_sample: [...]}`
- `POST /model/switch` `{model}` (admin) → `{active: ModelInfo}`

### Auditoria (admin/auditor)
- `GET /audit?limit=50&offset=0&action=&user_id=&q=` → `{items: AuditEntry[], total}`
- `GET /audit/{id}` → `AuditEntry`
- `GET /audit/verify` → `{ok: boolean, checked: number, broken_at: number | null}` (verifica a cadeia de hashes — trilha à prova de adulteração)
- `GET /audit/actions` → `string[]` (valores distintos de `action`)

### Sistema
- `GET /health` → `{status:"ok"|"degraded", version, env, llm: {provider, model, reachable}, embeddings: {...}, db: "ok", vectorstore: {chunks}}`
- `GET /metrics` → Prometheus

## Ações de auditoria (valores de `action`)
`auth.login`, `auth.login_failed`, `auth.logout`, `patient.view`, `assistant.chat`, `assistant.blocked`, `assistant.feedback`, `workflow.start`, `workflow.alert`, `workflow.decision`, `workflow.finalize`, `alert.ack`, `knowledge.reindex`, `knowledge.search`, `model.switch`, `audit.verify`.
