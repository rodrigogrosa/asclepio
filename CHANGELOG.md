# Changelog

Todas as mudanças notáveis deste projeto são documentadas aqui (formato [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/), versionamento semântico).

## [2.0.0] — 2026-10-28 · Fase 4: monitoramento multimodal
### Adicionado
- Pacote `asclepio_multimodal` (workspace uv) com contrato único de resultado (`AnalysisResult`).
- **Vídeo**: OpenPose COCO (pesos oficiais da CMU via OpenCV DNN) em modo top-down sobre o YOLOv8n;
  perfis fisioterapia (amplitude, compensação de tronco, valgo, assimetria, consistência das
  repetições), quarto (queda, saída do leito, imobilidade) e cirurgia (área estéril, objetos não
  permitidos); quadros anotados, vídeo anotado H.264, gráficos e relatório Markdown automáticos.
- **Áudio**: Azure Speech to Text (pt-BR, timestamps por palavra) e Azure Text Analytics (Text
  Analytics for Health, sentimento, frases-chave) sobre texto anonimizado; acústica da voz com Praat
  (jitter, shimmer, HNR, pausas, ritmo) e eventos sonoros com AST treinado no AudioSet; indicadores de
  fadiga, dificuldade respiratória e alteração articulatória; modo local de reserva (Whisper + léxico).
- **Anomalias em tempo real**: detector online de sinais vitais (limites, z-score robusto, CUSUM/EWMA,
  Isolation Forest, antiflood), prescrições (salto de dose, dose máxima, alergia, suspensão abrupta,
  duplicidade) e mobilidade na internação (imobilidade, agitação noturna, saída do leito, queda);
  replay de séries reais do PhysioNet como monitor de beira-leito.
- **Fusão multimodal** tardia com regra de segurança e concordância entre modalidades.
- API `/monitoring/*`, `GET /alerts/stream` (SSE) e webhook opcional de alertas; tabelas
  `monitoring_analyses`, `prescription_events`, `mobility_readings`; permissões `monitoring:read/run`.
- Telas **Monitoramento** (tempo real, vídeo, áudio, histórico), detalhe da análise, painel
  multimodal no paciente e alertas em tempo real (toast) em todo o sistema.
- Avaliações reais (URFD, VOICED/PhysioNet, PhysioNet), relatório técnico, checklist e roteiro do
  vídeo da Fase 4; ADRs 0006–0008; `make azure-setup`, `make fase4-*`.
### Alterado
- PyTorch só-CPU no Linux (containers e CI); OpenCV fixado em 4.x (importador Caffe do OpenPose).

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
