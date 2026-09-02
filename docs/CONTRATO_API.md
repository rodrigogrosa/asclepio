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

---

## Autenticação real (v1.1): MFA TOTP, sessões/refresh, troca de senha, gestão de usuários

### Tipos adicionais
```ts
type User = { id: number; name: string; email: string; role: Role; crm: string | null; specialty: string | null; avatar_initials: string; permissions: string[];
  mfa_enabled: boolean; must_change_password: boolean; is_active: boolean; is_demo: boolean; last_login_at: string | null; created_at: string };
type TokenOut = { access_token: string; refresh_token: string; token_type: "bearer"; expires_in: number; refresh_expires_in: number; user: User; must_change_password: boolean };
type MfaChallenge = { mfa_required: true; mfa_token: string; expires_in: number; methods: ["totp", "recovery_code"] };
type Session = { id: number; created_at: string; last_used_at: string | null; expires_at: string; ip: string | null; user_agent: string | null; current: boolean };
```

### Endpoints de auth (novos/alterados)
- `POST /auth/login` `{email, password}` → **`TokenOut`** se o usuário não tem MFA, ou **`MfaChallenge`** (HTTP 200) se tem MFA ativo. 401 credenciais inválidas · 423 bloqueado.
- `POST /auth/mfa/verify` `{mfa_token, code}` → `TokenOut` (`code` = 6 dígitos do app autenticador **ou** um código de recuperação `XXXX-XXXX`). 401 código inválido (limite de tentativas).
- `POST /auth/refresh` `{refresh_token}` → `TokenOut` (rotação: o refresh antigo é revogado; reutilização de refresh revogado derruba **todas** as sessões do usuário — detecção de roubo).
- `POST /auth/logout` `{refresh_token?}` → `{ok:true}` (revoga a sessão atual; o access token deixa de valer imediatamente porque carrega `sid`).
- `POST /auth/logout-all` → `{ok:true, revoked:n}`.
- `POST /auth/change-password` `{current_password, new_password}` → `{ok:true}` (política de senha; revoga as **outras** sessões; limpa `must_change_password`).
- `GET /auth/mfa/setup` → `{secret, otpauth_uri, qr_svg}` (só se MFA ainda não ativo; `qr_svg` é um SVG inline para exibir).
- `POST /auth/mfa/enable` `{code}` → `{ok:true, recovery_codes: string[]}` (10 códigos de uso único — mostrar **uma vez**).
- `POST /auth/mfa/disable` `{password, code}` → `{ok:true}`.
- `GET /auth/sessions` → `Session[]` · `DELETE /auth/sessions/{id}` → `{ok:true}`.
- `GET /auth/me` → `User` (com os campos novos).

### Regras
- Access token: **30 min** (`ACCESS_TOKEN_EXPIRE_MINUTES`), claims `sub, role, sid, jti, iat, exp, iss`. Refresh token: **12 h** (`REFRESH_TOKEN_EXPIRE_HOURS`), opaco, guardado **hasheado** (SHA-256) na tabela `sessions`.
- Toda rota autenticada valida a sessão (`sid` ativo, não revogado, não expirado) além da assinatura do JWT.
- `must_change_password=true` → o frontend deve forçar a troca antes de usar o sistema (o backend bloqueia todas as rotas exceto `/auth/*` com **428 Precondition Required**).
- **Admins são obrigados a ter MFA**: se `role=admin` e `mfa_enabled=false`, o backend responde **428** com `{"detail":"MFA obrigatório para administradores", "code":"mfa_required_setup"}` em todas as rotas exceto `/auth/*` — o frontend leva para a tela de configuração do MFA.
- Segredo TOTP guardado **criptografado** (Fernet derivado do `SECRET_KEY`); códigos de recuperação guardados hasheados.

### Gestão de usuários (admin) — `users:manage`
- `GET /users` → `User[]`
- `POST /users` `{name, email, role, crm?, specialty?, password?}` → `{user: User, temporary_password: string | null}` (se `password` omitido, gera senha temporária forte; `must_change_password=true`).
- `PATCH /users/{id}` `{name?, role?, crm?, specialty?, is_active?}` → `User` (admin não pode remover o próprio papel de admin nem se desativar).
- `POST /users/{id}/reset-password` → `{temporary_password}` (revoga sessões do usuário; força troca).
- `POST /users/{id}/mfa/reset` → `{ok:true}` (desativa MFA do usuário — para quando perdeu o celular; auditado).
- Todas auditadas: `user.create`, `user.update`, `user.reset_password`, `user.mfa_reset`, `auth.mfa_enable`, `auth.mfa_disable`, `auth.mfa_verify`, `auth.mfa_failed`, `auth.refresh`, `auth.refresh_reuse_detected`, `auth.password_change`, `auth.session_revoke`.

### Usuários iniciais (seed)
| email | papel | senha | observação |
|---|---|---|---|
| `admin@asclepio.fiap` | admin | `ASCLEPIO_ADMIN_PASSWORD` (gerada pelo `make setup`, exibida uma vez, salva no `.env`) | `must_change_password=true`; MFA obrigatório no 1º acesso |
| `rodrigo.grosa2011@gmail.com` (Rodrigo Rosa) | admin | `ASCLEPIO_RODRIGO_PASSWORD` (idem) | idem |
| usuários de demonstração (dra.ana, dr.marcos, enf.carla, auditor) | medico/enfermagem/auditor | `Asclepio@2026` | só se `SEED_DEMO_USERS=true` (padrão em dev; **false em produção**); `is_demo=true` |

---

## Plataforma real (v1.2): perfis, catálogos e configuração

### Perfis e o que cada um vê (RBAC revisado)
| Área | admin | medico | enfermagem | auditor |
|---|---|---|---|---|
| Dashboard (clínico: pacientes/alertas/fluxos; admin: + sistema/modelo) | ✔ | ✔ (clínico) | ✔ (clínico) | ✔ (resumo) |
| Pacientes, contexto anonimizado | ✔ | ✔ | ✔ | — |
| Assistente (chat) | ✔ | ✔ | ✔ | — |
| Fluxos clínicos: executar | ✔ | ✔ | ✔ | — |
| Fluxos clínicos: aprovar/rejeitar | ✔ | ✔ | — | — |
| Alertas (ler/reconhecer) | ✔ | ✔ | ✔ | ler |
| Protocolos e documentos (leitura/busca) | ✔ | ✔ | ✔ | ✔ |
| Base de conhecimento: reindexar/gerir | ✔ | — | — | — |
| **IA & Modelos (modelo ativo, fine-tuning, avaliação, troca de modelo)** | ✔ | — | — | — |
| Detalhes técnicos dos grafos (LangGraph) | ✔ | — | — | — |
| Usuários / profissionais (CRM, especialidade) | ✔ | — | — | — |
| Catálogos (especialidades, setores) — gerir | ✔ | — | — | — |
| Auditoria | ✔ | — | — | ✔ |
| Configurações do sistema | ✔ | — | — | — |

Permissões novas: `system:internals` (grafos/mermaid — admin), `catalog:read` (todos), `catalog:manage` (admin), `settings:read` (admin). `model:read` passa a ser **somente admin**. `GET /assistant/graph` e `GET /workflows/graph` exigem `system:internals`. O campo `User.permissions` continua vindo no login — o frontend monta o menu a partir dele (não por papel fixo).

### Configuração pública (sem autenticação)
- `GET /public/config` → `{app_name, hospital_name, hospital_short_name, version, demo_mode: boolean, mfa_required_roles: string[], support_email: string | null}`
  - `demo_mode` = `SEED_DEMO_USERS` (mostra a lista de usuários de demonstração no login **somente** quando true).
  - `hospital_name` vem de `APP_HOSPITAL_NAME` (padrão "Hospital Universitário"), `hospital_short_name` de `APP_HOSPITAL_SHORT_NAME` (padrão "HU"). **A interface não deve mostrar "fictício", "Tech Challenge" ou "FIAP"** — isso fica só na documentação.

### Catálogos
```ts
type Specialty = { id: number; name: string; code: string | null; active: boolean; professionals_count: number };
type Sector = { id: number; name: string; kind: "pronto_socorro" | "internacao" | "uti" | "ambulatorio" | "cirurgico" | "outro"; active: boolean; patients_count: number };
```
- `GET /catalog/specialties?include_inactive=false` → `Specialty[]` (`catalog:read`) · `POST /catalog/specialties` `{name, code?}` · `PATCH /catalog/specialties/{id}` `{name?, code?, active?}` · `DELETE /catalog/specialties/{id}` (só se sem profissionais; senão 409) — `catalog:manage`.
- `GET /catalog/sectors` → `Sector[]` · `POST/PATCH/DELETE /catalog/sectors/...` idem.
- Seed: ~30 especialidades médicas brasileiras (CFM) e os setores usados pelos pacientes.
- `User` ganha `specialty_id: number | null` e `sector_id: number | null` (além de `specialty`/`crm` textuais para exibição). `POST/PATCH /users` aceitam `specialty_id`, `sector_id`; para `role=medico` o `crm` é **obrigatório** (formato `CRM 123456-UF` ou `123456-UF`) e a especialidade obrigatória.
- `GET /users?role=&active=&q=` com filtros; `GET /users/{id}`.

### Dashboard por perfil
`GET /dashboard/stats` devolve **sempre** os indicadores clínicos; os campos `model`, `guardrail_blocks_today`, `system` só aparecem para quem tem `model:read`/`audit:read` (para os demais vêm `null`). Novo bloco `my_work` (para medico/enfermagem): `{pending_approvals: WorkflowRun[] (aguardando_aprovacao), my_open_alerts: number, my_conversations_today: number}`.

---

## Central de documentação (v1.3) — evidências acadêmicas dentro da plataforma

Permissão nova: `docs:read` (admin e auditor). Menu "Documentação" no frontend.

```ts
type DocFormat = "md" | "pdf" | "mmd";
type HubDocument = { id: string; title: string; description: string; format: DocFormat; filename: string;
  size_bytes: number; updated_at: string | null; readable: boolean; downloadable: boolean };
type HubCategory = { id: string; title: string; description: string; documents: HubDocument[] };
```

- `GET /docs-hub` → `{categories: HubCategory[], total: number}` — biblioteca curada (relatórios, processo de desenvolvimento, arquitetura/ADRs, dados & ML, segurança, operação, diagramas).
- `GET /docs-hub/{doc_id}` → `HubDocument & {content: string}` — conteúdo para leitura (só `md`/`mmd`); imagens relativas já vêm **embutidas em base64** (renderizam direto no MarkdownView); diagramas `.mmd` vêm com `content` puro Mermaid (renderizar com o MermaidGraph).
- `GET /docs-hub/{doc_id}/download` → arquivo original (`Content-Disposition: attachment`), inclusive PDFs.
- 404 para id desconhecido; sem acesso a caminhos fora da lista curada (não há endpoint por caminho livre).
