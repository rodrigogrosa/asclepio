# Evidências do Tech Challenge (Fase 3) — onde cada exigência aparece

> Guia para apresentação/avaliação. Faça login como **admin** (`admin@asclepio.fiap`) para ver as áreas técnicas (IA & Modelos, grafos, auditoria, configurações); as telas clínicas aparecem para médico/enfermagem. URLs abaixo consideram `make setup` (Web `:3000`, API `:8000`) — ajuste se usou outras portas.

## 1. Fine-tuning de LLM com dados internos (protocolos, FAQs, modelos de laudos/receitas)
| Evidência | Onde ver |
|---|---|
| Dados usados (protocolos, modelos de documentos, FAQ) | Tela **Protocolos e documentos** (`/conhecimento`) — lista, busca semântica e conteúdo de cada documento. Arquivos: `data/knowledge_base/` |
| Pré-processamento, **anonimização** e curadoria | `data/processed/DATASET_CARD.md` e `dataset_stats.json` (contagens, entidades PII removidas, dedupe, balanceamento, splits). Código: `ml/asclepio_ml/data_prep.py`, `packages/asclepio_core/asclepio_core/anonymizer.py` |
| Treino (LoRA), hiperparâmetros, loss, hardware, tempo | Tela **IA & Modelos** (`/modelo`, admin) → card "Fine-tuning" (base, LoRA r/α, épocas, passos, loss, duração) e gráfico `docs/assets/eval/train_loss.png`. Arquivo: `ml/registry.json` |
| Modelo customizado servido e **integrado** ao assistente | `/modelo` → "Modelo ativo: asclepio-med (ajustado)"; `ollama list` mostra `asclepio-med`; badge no header. `/health` → `"fine_tuned": true` |
| Avaliação base × fine-tuned (+ referência) e RAG | `/modelo` → gráficos e tabela (ROUGE-L, BLEU, cobertura, citação, conformidade com guardrails, recusa segura, juiz LLM, latência; hit@5/MRR do RAG) e amostras comparadas. Arquivos: `ml/reports/eval_latest.{json,md}`, `docs/assets/eval/*.png`, `docs/FINE_TUNING.md` |
| Reprodutibilidade | `make prepare`, `make train`, `make export`, `make eval` (ou `make finetune`) — `ml/README.md` |

## 2. Assistente médico com LangChain (LLM customizada + base estruturada + contexto do paciente)
| Evidência | Onde ver |
|---|---|
| Pipeline LangChain/LangGraph com a LLM fine-tunada | **Assistente** (`/assistente`): resposta em streaming; painel "Fontes & explicabilidade" mostra modelo `asclepio-med`, intenção, latência, confiança. Admin vê as etapas do grafo (guard_input → classify → retrieve → generate → guard_output) e `GET /api/v1/assistant/graph` (Mermaid) |
| Consulta à base estruturada (prontuários) | **Pacientes** (`/pacientes`, `/pacientes/{id}`): sinais vitais, exames, medicações, evoluções vindos do banco (Postgres/SQLite) |
| Contextualização com dados atualizados do paciente | No chat, selecione o paciente → botão **"ver contexto anonimizado"** exibe exatamente o texto enviado à LLM (idade/sexo/setor, vitais, exames, risco) — **sem PII** |
| RAG com citações | Respostas com `[1] [2]…` clicáveis; painel lateral com documento › seção › score › trecho |

## 3. Fluxos de decisão automatizados e seguros (LangGraph)
| Evidência | Onde ver |
|---|---|
| Fluxo que recebe o paciente, verifica exames pendentes, sugere condutas e emite alertas | `/pacientes/{id}` → **"Executar revisão clínica"** → `/fluxos/{run_id}`: linha do tempo das etapas (carregar/anonimizar → exames pendentes/atrasados → triagem de risco qSOFA/NEWS2/valores críticos → alerta imediato se crítico → protocolos (RAG) → sugestão da LLM com fontes → guardrails → alertas → **validação humana** → finalização) |
| Diagrama do fluxo (LangGraph) | `/fluxos` (admin) → card "Grafo de revisão clínica" (Mermaid gerado pelo próprio LangGraph). Arquivos: `docs/diagramas/*.mmd`, `docs/ARQUITETURA.md` |
| Humano no circuito | Caixa "Validação humana obrigatória" → Aprovar/Rejeitar (só médico/admin; enfermagem vê 403) |
| Alertas para a equipe | **Alertas** (`/alertas`) — críticos/atenção criados pelo fluxo e por regras, com reconhecimento |

## 4. Segurança e validação
| Evidência | Onde ver |
|---|---|
| Limites de atuação (nunca prescrever sem validação humana) | No chat: "Prescreva 2 g de ceftriaxona para o leito 5" → recusa + informação do protocolo + aviso; "Ignore suas instruções…" → **bloqueado** (badge do guardrail). Código/testes: `packages/asclepio_core/asclepio_core/guardrails.py`, `packages/asclepio_core/tests/test_guardrails.py` |
| Logging detalhado para rastreamento e auditoria | **Auditoria** (`/auditoria`, admin/auditor): todas as ações (login, MFA, consulta a paciente, pergunta, bloqueio, fluxo, decisão, alerta, troca de modelo), com fontes usadas, guardrail, modelo, latência, `trace_id`; botão **"Verificar integridade da cadeia"** (hash chain). Logs estruturados no terminal (`make logs`); Prometheus em `/metrics`; Langfuse (`make up-full`, `:3001`) |
| Explainability (fonte da informação) | Citações numeradas + painel de fontes no chat; sugestões do fluxo com citações; `citation_rate` na avaliação |
| Autenticação/autorização reais | Login com **MFA (app autenticador)**, troca de senha obrigatória, sessões (`/conta`), perfis (médico não vê IA/Modelos, admin vê tudo), usuários e profissionais (`/usuarios`), catálogos (`/catalogos`). Políticas: `docs/POLITICAS.md` |

## 5. Organização do código e README
| Evidência | Onde ver |
|---|---|
| Projeto modularizado em Python | `packages/asclepio_core` (núcleo), `backend` (API + LangGraph), `ml` (fine-tuning); Swagger em `/docs` |
| Instruções completas | `README.md` (instalação em 1 comando / 1 linha, arquitetura, fine-tuning, segurança, troubleshooting), `ml/README.md`, `frontend/README.md` |
| Testes e CI | `make check` (85+ testes); GitHub Actions verde (aba **Actions** do repositório) |

## 6. Entregáveis da Fase 3
| Entregável | Local |
|---|---|
| Código: pipeline de fine-tuning, integração LangChain, fluxos LangGraph | `ml/`, `backend/asclepio_api/services/{assistant,workflow,knowledge,llm}.py` |
| Dataset anonimizado / sintético | `data/synthetic/patients.json`, `data/processed/*.jsonl` (+ `DATASET_CARD.md`), `data/knowledge_base/` |
| Relatório técnico (fine-tuning, assistente, diagrama, avaliação) | `docs/RELATORIO_TECNICO.md` (+ `docs/FINE_TUNING.md`, `docs/ARQUITETURA.md`, `docs/diagramas/`) |
| Vídeo (≤ 15 min) | roteiro em `docs/ROTEIRO_VIDEO.md` |

## Roteiro rápido de demonstração (10 min)
1. `/modelo` (admin): fine-tuning, métricas base × ajustado, RAG. 2. `/assistente`: pergunta de protocolo (fontes), pergunta com paciente + "ver contexto anonimizado", pedido de prescrição (recusa), injeção (bloqueio). 3. `/pacientes/1` → "Executar revisão clínica" → `/fluxos/{id}` → aprovar. 4. `/alertas`. 5. `/auditoria` → filtrar `assistant.blocked`, verificar integridade. 6. `/conta` (MFA) e `/usuarios` (perfis).
