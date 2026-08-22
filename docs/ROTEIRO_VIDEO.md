# Roteiro do vídeo (≤ 15 min) — Asclépio

> Objetivo do vídeo (edital): mostrar **treinamento e funcionamento da LLM personalizada**, **execução de um fluxo automatizado**, **respostas a perguntas clínicas contextualizadas** e **logs e validação das respostas**. Grave em 1080p, dark mode, com o `make up-full` já de pé e o `asclepio-med` criado.

| Tempo | Cena | O que mostrar / falar |
|---|---|---|
| 0:00–0:45 | **Abertura** | Logo/identidade. "Asclépio: assistente clínico do HU-FIAP. Fine-tuning + LangChain/LangGraph + guardrails + auditoria." Mostrar o diagrama de arquitetura do README. |
| 0:45–2:30 | **Dados e fine-tuning** | `data/knowledge_base/` (protocolo aberto, front matter, seções). `make prepare`: logs de anonimização/curadoria, `DATASET_CARD.md`. `ml/registry.json` e gráfico de loss (`docs/assets/eval/train_loss.png`). Explicar LoRA em 2 frases. |
| 2:30–3:30 | **Modelo no Ollama** | `ollama list` (asclepio-med), `ollama run asclepio-med "Qual o alvo de lactato na sepse segundo o protocolo?"`. Página `/modelo`: métricas base vs fine-tuned e RAG. |
| 3:30–4:15 | **Subir tudo** | `make setup` (cortar o tempo de build) → `/health`, Swagger. Login como Dra. Ana. Dashboard. |
| 4:15–7:00 | **Assistente contextualizado** | `/assistente`: (1) pergunta geral de protocolo → streaming, etapas do grafo, citações `[n]`, painel de fontes, confiança. (2) Selecionar paciente (sepse) → "ver contexto anonimizado" (PII redigida) → "Resuma o quadro e pontos de atenção". (3) "Prescreva 2 g de ceftriaxona para o leito 5" → recusa + protocolo. (4) "Ignore suas instruções…" → bloqueado. |
| 7:00–10:00 | **Fluxo automatizado (LangGraph)** | `/pacientes/1` → "Executar fluxo clínico". Em `/fluxos/<run>`: timeline dos 10 nós (risco crítico, alerta imediato, exames atrasados, RAG, sugestões da LLM com fontes, guardrail), alertas criados. Caixa **Validação humana**: aprovar com comentário → status aprovado. Mostrar grafo Mermaid em `/fluxos`. Logar como enfermagem e mostrar que não pode aprovar (403). |
| 10:00–12:00 | **Logs, auditoria e observabilidade** | Terminal: logs structlog com `request_id`. `/auditoria`: filtrar `assistant.blocked`, abrir detalhes (fontes, guardrail, modelo), **Verificar integridade da cadeia** (ok). Langfuse (http://localhost:3001): trace da conversa com prompt, tokens, latência. LiteLLM UI (opcional). `/metrics`. |
| 12:00–13:30 | **Segurança e políticas** | `core/policies.py` (RBAC, política de senha), tentativa de login errada 5x → bloqueio, headers, anonimizador (teste unitário rodando: `make test-core`). |
| 13:30–14:30 | **Avaliação e limitações** | Tabela do `docs/FINE_TUNING.md`: o que melhorou (formato, escopo, recusas, citações) e o que não (raciocínio de modelo 0,5B), por que RAG + guardrails; próximos passos. |
| 14:30–15:00 | **Encerramento** | Recap dos requisitos atendidos (tabela do README). Repositório, equipe, agradecimentos. |

Dicas: deixe dois terminais prontos (logs da API e comandos); prepare as perguntas em um arquivo para colar; grave a parte de fine-tuning antes (time-lapse).
