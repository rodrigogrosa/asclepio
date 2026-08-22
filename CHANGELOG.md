# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui (formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versionamento semântico).

## [1.0.0] — 2026-08-21
### Adicionado
- `asclepio_core`: anonimizador de PII, regras clínicas (qSOFA, NEWS2, valores críticos, risco), guardrails de entrada/saída, loader/chunking da base de conhecimento, gerador de pacientes sintéticos.
- Backend FastAPI: autenticação JWT com política de senha e bloqueio, RBAC declarativo, rate limit, headers de segurança, auditoria append-only com cadeia de hashes, métricas Prometheus, logs estruturados.
- Assistente (grafo LangGraph) com RAG (Chroma + nomic-embed-text), contexto de paciente anonimizado, streaming SSE, citações e guardrails.
- Fluxo de revisão clínica (grafo LangGraph) com regras determinísticas, alertas, regeneração guiada por guardrails e validação humana (`interrupt`).
- Fábrica de LLM: Ollama (modelo fine-tunado `asclepio-med` com fallback), LiteLLM, OpenAI-compatible e modo `fake`; tracing no Langfuse.
- Frontend Next.js com identidade FIAP: dashboard, assistente, pacientes, fluxos, alertas, base de conhecimento, modelo, auditoria; modo mock.
- Pipeline de ML: preparação/anonimização/curadoria do dataset, fine-tuning LoRA, exportação para Ollama, avaliação base vs fine-tuned e RAG.
- Base de conhecimento fictícia (16 protocolos, 10 modelos de documento, 167 FAQs) e 233 instruções seed.
- Docker Compose (Postgres, API, Web; perfis Ollama, LiteLLM, Langfuse v3, ML), `make setup` automatizado, CI GitHub Actions, pre-commit, Dev Container.
- Documentação: README, relatório técnico, arquitetura, políticas, ADRs, contrato da API, identidade visual, roteiro do vídeo.
