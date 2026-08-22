# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui (formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versionamento semântico).

## [1.2.0] — 2026-08-22
### Adicionado
- Plataforma por perfil: RBAC revisado (IA & Modelos, gestão da base, usuários, catálogos e detalhes técnicos só para admin), catálogo de especialidades e setores, cadastro de profissionais com CRM/especialidade validados, dashboard por perfil ("Meu trabalho"), configuração pública do hospital (`APP_HOSPITAL_NAME`), interface sem textos acadêmicos.

## [1.1.0] — 2026-08-22
### Adicionado
- Autenticação forte: MFA TOTP (app autenticador) com códigos de recuperação e obrigatoriedade para admins; sessões com refresh token rotativo, revogação e detecção de reuso; troca de senha obrigatória no primeiro acesso; gestão de usuários pelo admin; usuários reais (admin e Rodrigo Rosa) com senhas geradas pelo `make setup`; telas de conta/MFA/sessões/usuários no frontend.
- Amostras de PubMedQA/MedQuAD no dataset de fine-tuning (≤ 10 %) e novo ciclo de treino/avaliação; `make docs-metrics`; instalador de 1 linha (`install.sh`).

## [1.0.0] — 2026-08-21
### Adicionado
- `asclepio_core`: anonimizador de PII, regras clínicas (qSOFA, NEWS2, valores críticos, risco), guardrails de entrada/saída, loader/chunking da base de conhecimento, gerador de pacientes sintéticos.
- Backend FastAPI: autenticação JWT com política de senha e bloqueio, RBAC declarativo, rate limit, headers de segurança, auditoria append-only com cadeia de hashes, métricas Prometheus, logs estruturados.
- Assistente (grafo LangGraph) com RAG (Chroma + nomic-embed-text), contexto de paciente anonimizado, streaming SSE, citações e guardrails.
- Fluxo de revisão clínica (grafo LangGraph) com regras determinísticas, alertas, regeneração guiada por guardrails e validação humana (`interrupt`).
- Fábrica de LLM: Ollama (modelo fine-tunado `asclepio-med` com fallback), LiteLLM, OpenAI-compatible e modo `fake`; tracing no Langfuse.
- Frontend Next.js com identidade FIAP: dashboard, assistente, pacientes, fluxos, alertas, base de conhecimento, modelo, auditoria; modo mock.
- Pipeline de ML: preparação/anonimização/curadoria do dataset, fine-tuning LoRA, exportação para Ollama, avaliação base vs fine-tuned e RAG.
- Base de conhecimento fictícia (16 protocolos, 10 modelos de documento, 167 FAQs), 233 instruções seed e amostras de PubMedQA/MedQuAD (≤ 10 %) no dataset de fine-tuning.
- Docker Compose (Postgres, API, Web; perfis Ollama, LiteLLM, Langfuse v3, ML), `make setup` automatizado, CI GitHub Actions, pre-commit, Dev Container.
- Documentação: README, relatório técnico, arquitetura, políticas, ADRs, contrato da API, identidade visual, roteiro do vídeo.
