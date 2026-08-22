# Arquitetura — Asclépio

## 1. Visão geral

O Asclépio é um **assistente clínico de apoio à decisão** composto por quatro blocos:

| Bloco | Tecnologia | Responsabilidade |
|---|---|---|
| `asclepio_core` | Python puro (pydantic, regex, Faker) | Código compartilhado e **sem dependência de rede**: anonimização de PII, regras clínicas (qSOFA, NEWS2, valores críticos), guardrails, leitura/chunking da base de conhecimento, geração de pacientes sintéticos. |
| `backend` | FastAPI · SQLAlchemy 2 (async) · LangChain 1.x · LangGraph 1.x · Chroma · structlog · slowapi · Prometheus | API REST/SSE, autenticação/autorização, persistência, dois grafos LangGraph (chat e revisão clínica), RAG, auditoria, integração com LLMs. |
| `frontend` | Next.js 16 (App Router) · Tailwind v4 · Recharts · Mermaid | Interface para médicos/enfermagem/auditoria com identidade FIAP. |
| `ml` | transformers · PEFT · TRL · datasets · evaluate | Pipeline de fine-tuning (LoRA), exportação para Ollama e avaliação. |

Serviços de apoio: **Ollama** (serve o `asclepio-med`, o fallback `llama3.1:8b` e os embeddings `nomic-embed-text`), **Postgres** (prontuários, conversas, fluxos, auditoria — SQLite em dev), **LiteLLM** (gateway OpenAI-compatible opcional), **Langfuse** (traces de LLM opcional).

## 2. Diagrama de componentes

```mermaid
flowchart TB
  subgraph Client[Navegador]
    FE[Next.js · App Router]
  end
  subgraph Api[FastAPI · backend/asclepio_api]
    MW[Middlewares<br/>request-id · security headers · body limit · CORS · rate limit]
    R[Routers<br/>auth · dashboard · patients · assistant · workflows · alerts · knowledge · model · audit · system]
    S1[services/assistant.py<br/>grafo do chat]
    S2[services/workflow.py<br/>grafo de revisão clínica]
    S3[services/knowledge.py<br/>RAG · Chroma]
    S4[services/patients.py<br/>contexto anonimizado · risco]
    S5[services/llm.py<br/>fábrica de modelos · Langfuse]
    AU[core/audit.py<br/>cadeia de hashes]
    PO[core/policies.py<br/>RBAC · senha]
  end
  subgraph Core[asclepio_core]
    AN[anonymizer]
    CR[clinical_rules]
    GD[guardrails]
    KB[knowledge]
  end
  DB[(Postgres/SQLite)]
  VS[(Chroma)]
  CK[(Checkpoints LangGraph<br/>SQLite)]
  OL[Ollama]
  LL[LiteLLM]
  LF[Langfuse]
  FE --> MW --> R
  R --> S1 & S2 & S3 & S4 & AU & PO
  S1 & S2 --> S3 & S4 & S5 & AU
  S4 --> AN & CR
  S1 & S2 --> GD
  S3 --> KB & VS
  S2 --> CK
  R --> DB
  S5 --> OL
  S5 -.-> LL --> OL
  S5 -.-> LF
```

## 3. Fluxo do chat (LangGraph)

```mermaid
sequenceDiagram
  autonumber
  participant U as Médico (Web)
  participant A as API /assistant/chat/stream
  participant G as Grafo LangGraph
  participant C as asclepio_core
  participant V as Chroma (RAG)
  participant L as LLM (asclepio-med)
  participant D as Banco / Auditoria
  U->>A: POST {message, patient_id}
  A->>D: conversa + histórico + prontuário
  A->>C: build_context(paciente) → texto SEM PII + risco
  A->>G: astream_events(state)
  G->>C: guard_input (PII, injection, prescrição, escopo)
  alt bloqueado
    G-->>A: resposta padrão de bloqueio
  else
    G->>G: classify_intent
    G->>V: retrieve (top-k, boost por protocolos sugeridos)
    G-->>A: event step/citations
    G->>L: generate (system prompt + trechos [n] + contexto paciente + histórico)
    L-->>A: tokens (SSE)
    G->>C: guard_output (linguagem prescritiva, PII, aviso)
  end
  A->>D: persiste mensagens + auditoria (fontes, guardrail, modelo, latência)
  A-->>U: event done (citações, guardrail, confiança, trace_id)
```

Grafo (gerado por `graph.get_graph().draw_mermaid()`): [`diagramas/grafo_chat_langgraph.mmd`](diagramas/grafo_chat_langgraph.mmd).

## 4. Fluxo de revisão clínica (LangGraph com validação humana)

```mermaid
flowchart TD
  S([Início]) --> LP[load_patient<br/>prontuário → contexto anonimizado]
  LP --> PE[check_pending_exams<br/>pendentes / atrasados]
  PE --> TR[triage_risk<br/>qSOFA · NEWS2 · valores críticos]
  TR -- crítico --> IA[emit_immediate_alerts<br/>alerta crítico ANTES da LLM]
  TR -- demais --> RP
  IA --> RP[retrieve_protocols<br/>RAG com boost dos protocolos sugeridos]
  RP --> SC[suggest_conduct<br/>LLM fine-tunada cita fontes]
  SC --> VG[validate_guardrails]
  VG -- reprovado 1x --> SC
  VG --> EA[emit_alerts<br/>exames atrasados · valores críticos · gatilhos]
  EA --> HR{{human_review<br/>interrupt ⏸}}
  HR -- médico aprova/rejeita --> FZ[finalize<br/>auditoria]
  FZ --> E([Fim])
```

Pontos de projeto:
- **Regras antes da LLM**: o risco e os alertas críticos não dependem do modelo — são código determinístico (`asclepio_core.clinical_rules`).
- **Checkpoint persistente**: `AsyncSqliteSaver` em `data/checkpoints/langgraph.sqlite`; o `run_id` é o `thread_id`. A API retoma com `Command(resume=decisão)`.
- **Cada nó registra um passo** (status, duração, resumo, dados) → timeline no frontend e auditoria.
- Grafo gerado: [`diagramas/grafo_revisao_clinica_langgraph.mmd`](diagramas/grafo_revisao_clinica_langgraph.mmd).

## 5. RAG e explicabilidade

1. `asclepio_core.knowledge` lê os `.md` (front matter YAML) e o FAQ JSONL; faz **chunking por seção H2** (máx. 1.400 caracteres, com cabeçalho "Título › Seção").
2. `services/knowledge.py` indexa no **Chroma** (cosine) com embeddings `nomic-embed-text` (Ollama) — ou `DeterministicFakeEmbedding` nos testes. Um *manifest* com hash dos arquivos evita reindexar sem mudanças.
3. A busca devolve `{source_id, title, section, score, chunk}`; os protocolos sugeridos pelas regras clínicas recebem *boost*.
4. O prompt numera os trechos `[n]`; o modelo é instruído a citar e listar "Fontes:". A resposta carrega as citações, e a auditoria guarda os IDs das fontes.
5. Confiança (`alta/media/baixa`) deriva do melhor score e das flags do guardrail.

## 6. Dados

- **Prontuários**: `asclepio_core.synthetic` gera 24 pacientes (cenários dirigidos para os protocolos: sepse, CAD, SCA, AVC, hipercalemia/LRA, IC, hipoglicemia, asma, delirium, anafilaxia, crise hipertensiva, ITU…) com sinais vitais, exames (alguns atrasados/críticos), medicações e evoluções **com PII fictícia** (CPF, telefone, endereço) para demonstrar o anonimizador. O seed ancora os horários no momento da carga.
- **Base de conhecimento**: `data/knowledge_base/` (16 protocolos, 10 modelos, 167 FAQs) — conteúdo fictício/educacional.
- **Dataset SFT**: `data/processed/{train,val,test}.jsonl` gerado por `ml prepare` (ver `DATASET_CARD.md`).

## 7. Observabilidade

- **Logs**: structlog (console em dev, JSON em prod) com `request_id` propagado por `contextvars`; cada evento de auditoria também é logado.
- **Métricas**: `prometheus-fastapi-instrumentator` em `/metrics`.
- **Traces de LLM**: `LLMFactory.run_config()` injeta o `CallbackHandler` do Langfuse (quando habilitado) com `session_id` (conversa/run), `user_id` e tags; o LiteLLM também envia traces (`success_callback: ["langfuse"]`).
- **Health**: `/health` verifica banco, alcance do Ollama, modelo resolvido e nº de chunks indexados.

## 8. Provedores de LLM

`LLM_PROVIDER` = `ollama` (padrão, local) | `litellm` (gateway) | `openai` (qualquer API compatível) | `fake` (testes). A fábrica resolve o modelo pedido (`asclepio-med`) e cai para `LLM_FALLBACK_MODEL` quando ele não existe no Ollama — a UI mostra se o modelo ativo é fine-tunado.

## 9. Deploy

`docker-compose.yml` com perfis: padrão (db, api, web), `ollama` (Ollama + init automático), `gateway` (LiteLLM), `observability` (LiteLLM + Langfuse v3 com ClickHouse/MinIO/Redis, inicialização *headless* com chaves conhecidas), `ml` (pipeline em container). Imagens multi-stage, usuário não-root, healthchecks. `scripts/bootstrap.sh` automatiza tudo.
