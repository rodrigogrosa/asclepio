# Processo de Desenvolvimento — memória descritiva do projeto
### Asclépio — Assistente Clínico Inteligente · Tech Challenge · Fase 3 · FIAP Pós-Tech IA para Devs (8IADT)

> Este documento é a **evidência acadêmica do processo**: descreve, etapa por etapa, *como* o projeto foi concebido, construído e validado — com objetivo, método, ferramentas, artefatos produzidos e critérios de qualidade de cada fase. Complementa o `RELATORIO_TECNICO.md` (que descreve *o que* foi entregue) e o `EVIDENCIAS.md` (que mostra *onde* cada exigência aparece no sistema).

---

## 1. Introdução

O edital da Fase 3 pede um assistente virtual médico treinado com dados próprios do hospital (fine-tuning), integrado via LangChain a bases estruturadas e ao contexto do paciente, com fluxos de decisão automatizados e seguros (LangGraph), guardrails, logging/auditoria e explicabilidade. A equipe estabeleceu, além do edital, quatro princípios de engenharia que orientaram todas as decisões:

1. **Didática** — código comentado em pt-BR explicando o *porquê*, documentação que ensina.
2. **Reprodutibilidade** — qualquer avaliador instala com um comando e obtém o mesmo sistema; sementes fixas nos processos estocásticos; nenhum serviço pago.
3. **Segurança por construção** — políticas, guardrails e anonimização como **código testável**, não como texto.
4. **Honestidade experimental** — métricas reais (base × fine-tuned × referência), limitações explícitas.

**Método de trabalho.** Desenvolvimento incremental orientado a requisitos: (i) extração dos requisitos do edital para uma tabela de conformidade; (ii) definição de contratos (API e identidade visual) antes da implementação, permitindo trabalho paralelo de frontend, backend e ML; (iii) integração e verificação contínuas (testes automatizados + validação manual no navegador a cada incremento); (iv) registro de decisões em ADRs e do histórico em commits atômicos. Ferramentas de assistência de código baseadas em IA foram utilizadas como apoio de produtividade (*pair programming*), com todas as decisões de arquitetura, revisão e validação realizadas pela equipe — prática alinhada ao próprio tema do curso.

**Stack.** Python 3.12 (uv), LangChain/LangGraph 1.x, Transformers/PEFT/TRL, Ollama, ChromaDB, FastAPI, SQLAlchemy 2, PostgreSQL, Next.js 16/React 19/Tailwind 4, Docker Compose, GitHub Actions, LiteLLM, Langfuse.

---

## 2. Etapas do desenvolvimento

Cada etapa segue o formato: **Objetivo → Método → Artefatos → Validação → Resultado**.

### Etapa 1 — Análise do edital e engenharia de requisitos
- **Objetivo:** transformar o PDF do desafio em requisitos verificáveis.
- **Método:** leitura estruturada do edital; extração de 17 requisitos (técnicos e de entrega); para cada um, definição antecipada do *critério de evidência* (que tela, arquivo ou comando comprovaria o atendimento). Requisitos ampliados pela equipe: autenticação forte, perfis de acesso, observabilidade de LLM (LiteLLM/Langfuse), instalação 100 % automatizada.
- **Artefatos:** tabela "Checklist de conformidade" (abertura do `RELATORIO_TECNICO.md`); `EVIDENCIAS.md`.
- **Validação:** revisão cruzada requisito ↔ evidência ao final de cada fase.
- **Resultado:** 17/17 requisitos rastreáveis (o vídeo, único item externo ao repositório, tem roteiro pronto).

### Etapa 2 — Concepção do produto e identidade visual
- **Objetivo:** dar ao sistema identidade própria e coerente com a instituição.
- **Método:** *naming* (Asclépio, deus grego da medicina — o bastão com serpente é símbolo universal da profissão); construção do logotipo em SVG (bastão + serpente + nós de rede neural); definição de *design tokens* inspirados na identidade FIAP (rosa `#ED145B` sobre quase-preto `#0B0B10`, Montserrat/Inter), verificados visualmente em três tamanhos de aplicação.
- **Artefatos:** `docs/assets/brand/*.svg`, `docs/IDENTIDADE_VISUAL.md`.
- **Validação:** renderização no navegador (256/96/48 px) e no favicon.

### Etapa 3 — Arquitetura, contratos e decisões
- **Objetivo:** desenhar uma arquitetura que permitisse paralelismo de construção e evolução segura.
- **Método:** monorepo com três pacotes Python (núcleo compartilhado `asclepio_core`, API, pipeline de ML) + frontend; **contrato de API escrito antes do código** (`CONTRATO_API.md`, tipos TypeScript e endpoints), funcionando como especificação executável para o frontend; decisões relevantes registradas como ADRs com alternativas e consequências.
- **Artefatos:** `docs/ARQUITETURA.md`, `docs/CONTRATO_API.md` (v1 → v1.3), `docs/adr/0001..0005`.
- **Validação:** o frontend foi construído contra o contrato **antes** de o backend existir (modo *mock*), e a integração posterior não exigiu mudanças de contrato — evidência da qualidade da especificação.
- **Decisões-chave (resumo):** grafos LangGraph determinísticos com `interrupt` em vez de agente livre (ADR-0002); LoRA em modelo pequeno servido no Ollama (ADR-0003); auditoria com cadeia de hashes (ADR-0004); LiteLLM/Langfuse opcionais por perfil de composição (ADR-0005).

### Etapa 4 — Base de conhecimento clínica (dados "do hospital")
- **Objetivo:** criar o corpus institucional fictício exigido pelo edital (protocolos, FAQs, modelos de documentos).
- **Método:** redação de **16 protocolos clínicos** (sepse, SCA, AVC, CAD, PAC, TEV, anafilaxia, crise hipertensiva, IC, LRA, hipoglicemia/controle glicêmico, hipercalemia, asma/DPOC, dor, delirium, ITU) com estrutura padronizada (front matter YAML + 11 seções H2 fixas, incluindo limiares numéricos, tempos-alvo e fluxograma Mermaid), coerentes com diretrizes públicas (Surviving Sepsis Campaign, AHA/ACC/ASA, GINA/GOLD, ADA/SBD, NEWS2/qSOFA) e explicitamente marcados como fictícios; **10 modelos de documentos** (laudos, receita, evolução SOAP, sumário de alta etc.); **167 FAQs** vinculadas a protocolo/seção. A estrutura padronizada foi projetada **para o chunking por seção** do RAG (citações "PROT-001 › Conduta").
- **Artefatos:** `data/knowledge_base/**` (+ `README.md` com o esquema).
- **Validação:** validação sintática (front matter, seções, JSONL) por script; revisão cruzada FAQ ↔ protocolo (15 correções de consistência registradas).

### Etapa 5 — Dados sintéticos de pacientes e anonimização (LGPD)
- **Objetivo:** prover prontuários realistas sem qualquer dado real, e demonstrar anonimização de verdade.
- **Método:** gerador determinístico (`asclepio_core/synthetic.py`, Faker pt_BR, semente fixa) de **24 pacientes** — 18 cenários dirigidos aos protocolos (ex.: sepse com lactato de controle atrasado, CAD, SCA com curva de troponina pendente, hipercalemia em LRA) e internações estáveis. **PII fictícia é inserida de propósito** nas evoluções (nome, CPF, telefone, endereço, nome da mãe) para exercitar o anonimizador. O anonimizador (`asclepio_core/anonymizer.py`) combina regex determinísticas (CPF, CNS, RG, telefone, e-mail, CEP, endereço, data de nascimento) e detecção contextual de nomes, com pseudonimização consistente; é o **mesmo módulo** usado no preparo do dataset e em produção (propriedade de consistência treino↔uso).
- **Artefatos:** `packages/asclepio_core/asclepio_core/{synthetic,anonymizer}.py`, `data/synthetic/patients.json`, testes em `packages/asclepio_core/tests/`.
- **Validação:** 25 testes unitários do núcleo (falsos positivos clínicos, endereços, pseudonimização); teste de integração que garante **ausência de CPF/telefone/nome no contexto enviado à LLM**; contadores de PII expostos na interface ("N dados pessoais redigidos").

### Etapa 6 — Construção do dataset de fine-tuning
- **Objetivo:** transformar o corpus institucional em dados de instrução com pré-processamento, anonimização e curadoria auditáveis.
- **Método (pipeline `ml prepare`):** (a) 233 instruções-semente em 7 categorias (protocolo, documento, contexto de paciente, recusa de prescrição, fora de escopo, identidade/limites, privacidade); (b) geração programática de exemplos a partir de cada seção de protocolo, tabela de fármacos, FAQ e modelo de documento; (c) exemplos de *contexto de paciente* com **gabarito calculado por regras clínicas** (qSOFA/NEWS2/valores críticos) — supervisão sem intervenção manual; (d) augmentação por paráfrase templada; (e) anonimização integral; (f) curadoria: dedupe exato e aproximado, filtros de tamanho, balanceamento por categoria (teto de 1.300 na dominante), reforço do aviso de validação humana e das recusas; (g) *split* 85/7,5/7,5 **estratificado e agrupado** (paráfrases da mesma pergunta nunca se separam entre treino e teste — controle de vazamento); (h) amostras dos datasets sugeridos no edital (**PubMedQA** e **MedQuAD**, ≤ 10 %, rotuladas como "conhecimento público, não institucional").
- **Artefatos:** `ml/asclepio_ml/data_prep.py`, `data/processed/{train,val,test}.jsonl` (2.134 exemplos: 1.801/165/168), `dataset_stats.json`, `DATASET_CARD.md`.
- **Validação:** testes de preparo com *fixtures*; teste de segurança que falha se PII crua sobreviver no dataset.

### Etapa 7 — Fine-tuning (LoRA) e exportação para serving local
- **Objetivo:** especializar um LLM aberto no comportamento institucional, em hardware de estudante.
- **Método:** SFT com **LoRA** (r=16, α=32, dropout 0,05, projeções q/k/v/o/gate/up/down → 8,8 M parâmetros treináveis de 494 M ≈ 1,8 %) sobre `Qwen/Qwen2.5-0.5B-Instruct` (aberto, multilíngue, compatível com Apple Silicon/MPS e importável pelo Ollama); TRL `SFTTrainer` com *loss* apenas nos tokens do assistente; 2 épocas = 226 passos, batch efetivo 16, lr 2e-4 cosseno, seq. máx. 1.024, fp32/MPS. Exportação: fusão do adapter (`merge_and_unload`) → safetensors → `Modelfile` (system prompt institucional + template de chat) → `ollama create asclepio-med`. O modelo final é distribuído pela **Release v1.2.0 do GitHub** e baixado automaticamente pelo instalador.
- **Artefatos:** `ml/asclepio_ml/{train,export}.py`, `ml/configs/finetune.yaml` (comentado), `ml/registry.json`, `docs/assets/eval/train_loss.png`, Release `asclepio-med-v1.2.0.tar.gz`.
- **Validação/execução real:** treino em **21,7 min** (MacBook Apple Silicon), loss treino 0,82 · validação 1,38; problemas reais de engenharia documentados e resolvidos (mudanças de API do transformers 5, `rope_parameters` na importação pelo Ollama, limites de memória do MPS).

### Etapa 8 — Avaliação experimental do modelo
- **Objetivo:** medir, com controles, o que o fine-tuning mudou — e o que não mudou.
- **Método:** conjunto de teste *held-out* (120 amostras) + conjunto adversarial de segurança (15 prompts de prescrição direta/fora de escopo/injeção); quatro condições: base, fine-tuned (transformers), fine-tuned (Ollama) e **referência 16× maior sem fine-tuning** (`llama3.1:8b`). Métricas: ROUGE-L, BLEU, cobertura de termos-chave, taxa de citação, **conformidade com os guardrails** (avaliada pelo mesmo código de produção) e taxa de recusa correta, nota 1–5 por **LLM-juiz** (llama3.1:8b, rubrica de fidelidade/segurança/clareza, 60 amostras), latência. RAG avaliado com as 167 FAQs como consultas e o `protocolo_id` como gabarito (hit@5, MRR), contra baseline TF-IDF.
- **Artefatos:** `ml/asclepio_ml/{evaluate,metrics,rag_eval,plots}.py`, `ml/reports/eval_latest.{json,md}`, gráficos em `docs/assets/eval/`.
- **Resultados (última execução):** ROUGE-L 0,125 → **0,364**; BLEU 3,0 → **27,6**; conformidade com guardrails 0,77 → **0,95**; recusa correta 47 % → **80 %**; juiz 3,62 → 3,73; latência ~0,9 s (vs 2,7 s da referência). O `llama3.1:8b` obtém juiz maior (4,30) porém cita menos e obedece menos aos guardrails (0,84) — sustentando a tese *fine-tuning para forma/segurança + RAG para fatos + regras para decisões*. RAG: hit@5 **97,0 %**, MRR **0,910**. Limitações discutidas na §6.

### Etapa 9 — Assistente conversacional (LangChain/LangGraph + RAG)
- **Objetivo:** integrar a LLM customizada a um pipeline com recuperação citável e contexto do paciente.
- **Método:** grafo LangGraph de 6 nós (`guard_input → classify_intent → retrieve → generate → guard_output`, com desvio de bloqueio); RAG com ChromaDB (cosseno) e embeddings `nomic-embed-text`, chunking por seção com metadados e *boost* dos protocolos sugeridos pelas regras clínicas do paciente; contexto do prontuário **anonimizado e inspecionável pelo usuário**; streaming SSE token a token com eventos de progresso; citações numeradas ligadas a documento › seção › score; fábrica de provedores (Ollama/LiteLLM/OpenAI-compatível/*fake* determinístico para testes e CI).
- **Artefatos:** `backend/asclepio_api/services/{assistant,knowledge,llm,patients}.py`; diagrama gerado pelo próprio grafo (`docs/diagramas/grafo_chat_langgraph.mmd`).
- **Validação:** testes de API cobrindo citações, intenções, bloqueios e SSE; verificação qualitativa com o modelo real (respostas fiéis ao protocolo com fontes).

### Etapa 10 — Fluxos clínicos automatizados e seguros (LangGraph)
- **Objetivo:** materializar o requisito "receber informações do paciente → verificar exames pendentes → sugerir condutas → alertar a equipe", com segurança verificável.
- **Método:** grafo de **10 nós** com ramificações condicionais: risco calculado por **código determinístico** (qSOFA, NEWS2, valores críticos, exames atrasados) *antes* de qualquer LLM; alerta crítico imediato; sugestão da LLM com fontes e regeneração única guiada pelos guardrails; **`interrupt()` com checkpoint persistente** pausando o fluxo até a decisão de um médico (`Command(resume=...)`); cada nó registra passo (status, duração, resumo) para a linha do tempo e a auditoria.
- **Artefatos:** `backend/asclepio_api/services/workflow.py`, `packages/asclepio_core/asclepio_core/clinical_rules.py`, `docs/diagramas/grafo_revisao_clinica_langgraph.mmd`.
- **Validação:** teste de ciclo completo (execução → pausa → 403 para enfermagem → aprovação → finalização), teste de rejeição (alertas reconhecidos automaticamente), teste de paciente de baixo risco (sem alerta imediato).

### Etapa 11 — Segurança, governança e observabilidade
- **Objetivo:** limites de atuação, rastreabilidade e acesso dignos de um sistema real de saúde.
- **Método:** guardrails de entrada/saída como funções puras testáveis (injeção de prompt, pedido de prescrição, escopo, linguagem prescritiva, PII residual, aviso obrigatório); **autenticação forte** — senhas bcrypt com política, bloqueio por tentativas, **MFA TOTP** com códigos de recuperação (obrigatório para administradores), sessões com refresh token rotativo, revogação imediata e **detecção de reuso**; **RBAC por permissão** (`recurso:ação`) com perfis clínicos enxutos e áreas técnicas exclusivas do admin; **auditoria append-only com cadeia de hashes** (verificação de integridade exposta na interface e testada com adulteração deliberada do banco); logs estruturados com `trace_id` ponta a ponta, métricas Prometheus e traces de LLM no Langfuse (auto-hospedado, um comando).
- **Artefatos:** `asclepio_core/guardrails.py`, `backend/asclepio_api/core/{security,policies,audit,deps}.py`, `docs/POLITICAS.md`.
- **Validação:** 45 testes de API (fluxo completo de onboarding do admin com TOTP calculado em teste, rotação/reuso de refresh, lockout, RBAC por rota, quebra da cadeia de auditoria).

### Etapa 12 — Interface por perfil (visão de produto)
- **Objetivo:** experiência de sistema hospitalar real: cada papel vê apenas sua responsabilidade.
- **Método:** navegação montada a partir das **permissões** do usuário (não do papel); médico: pacientes, assistente, fluxos, alertas, protocolos; admin: + usuários & profissionais (CRM validado, especialidade/setor de catálogos administráveis), IA & Modelos, base de conhecimento, auditoria, configurações; detalhes técnicos (grafos, JSON) restritos a `system:internals`; identidade do hospital configurável (`APP_HOSPITAL_NAME`) obtida de endpoint público; central de **Documentação** (este acervo) para os perfis de avaliação.
- **Artefatos:** `frontend/**` (Next.js 16, contrato-first, modo mock completo), `docs/CONTRATO_API.md` §v1.2–v1.3.
- **Validação:** lint + typecheck + build na CI; verificação manual dos 4 perfis; guardas de rota com tela de acesso negado.

### Etapa 13 — Engenharia, DevEx e distribuição
- **Objetivo:** "clonou, rodou": reprodutibilidade total para qualquer avaliador.
- **Método:** Docker Compose com perfis (núcleo, `ollama`, `gateway`, `observability`, `ml`); `make setup`/`install.sh` (instalador de 1 linha) que verifica pré-requisitos, gera segredos, resolve portas em conflito, baixa modelos e o fine-tunado da Release, e valida a saúde; migração leve de esquema; CI com 4 jobs (lint+testes Python, frontend, build Docker, gitleaks+pip-audit); pre-commit; PDFs gerados por script (`make docs-pdf`).
- **Artefatos:** `docker-compose.yml`, `Makefile`, `scripts/{bootstrap.sh,build_report_pdf.py,update_report_metrics.py}`, `install.sh`, `.github/workflows/ci.yml`.
- **Validação:** instalação executada do zero na máquina da equipe e reproduzida por terceiros (ver Etapa 14); **88 testes automatizados** no total; CI verde no repositório público.

### Etapa 14 — Validação de campo e correções (engenharia de verdade)
- **Objetivo:** submeter o sistema a uso real por terceiros e corrigir com método.
- **Método/ocorrências (todas rastreáveis em commits e na auditoria):**
  1. *Instalação por colegas de turma* revelou falha de resolução de DNS do serviço Ollama quando o compose subia sem o perfil (`Name or service not known`) → correção: `COMPOSE_PROFILES` persistido no `.env` + mensagem de erro amigável (503) no lugar do erro técnico; cenário reproduzido em laboratório antes do conserto.
  2. *QR do MFA não escaneava* → diagnóstico com decodificação programática (OpenCV): densidade (versão 8) e URI com acentos; correção: URI `otpauth` mínima/ASCII (versão 6) e módulos maiores.
  3. *Conflitos de porta* com outros serviços nas máquinas (3000/4000/8000) → portas parametrizadas + detecção e orientação no instalador.
  4. *Credencial de admin divergente* → a **trilha de auditoria** evidenciou onboarding anterior (troca de senha + MFA) e o bloqueio por tentativas atuou como projetado; recuperação pelos fluxos administrativos.
- **Resultado:** além dos consertos, os episódios viraram evidência funcional dos mecanismos de segurança e observabilidade.

### Etapa 15 — Publicação e empacotamento das evidências
- **Objetivo:** entrega auditável.
- **Método:** repositório público com histórico de commits significativos; Release com o modelo; relatório técnico e guia de instalação em PDF; mapa de evidências; roteiro do vídeo; esta memória descritiva; central de Documentação dentro da própria plataforma.
- **Artefatos:** https://github.com/rodrigogrosa/asclepio (código, Releases, Actions) e `docs/**`.

---

## 3. Cronologia resumida (marcos por commit)

| Marco | Commit |
|---|---|
| v1.0 — plataforma completa: core (anonimização/regras/guardrails), API LangChain/LangGraph, frontend, pipeline de ML executado, Docker/CI/docs | `a10ba8a` |
| v1.2 — autenticação real (MFA/sessões), perfis por permissão, cadastros/catálogos, PubMedQA/MedQuAD no dataset, instalador de 1 linha | `cd8a17d` |
| Correções de campo: CI (`7beb7b2`), QR do MFA (`f2cd98c`, `274614d`), DNS do Ollama + erro amigável (`19ef4ae`, `89ad821`) | — |
| Evidências e entrega: checklist (`2ff12d2`), mapa de evidências (`233fa95`), PDFs (`f8ea1e2`, `493c40c`), modelo na Release + guia (`95a82ed`), zoom/exportação de diagramas (`e4c0da6`) | — |

## 4. Rastreabilidade

A matriz requisito → seção → evidência está no início do `RELATORIO_TECNICO.md`; o mapa requisito → tela/arquivo/comando, no `EVIDENCIAS.md`. Cada afirmação numérica deste documento é regenerável: `make prepare/train/export/eval` reproduz dados e métricas; `make docs-metrics` reinjeta os números na documentação.

## 5. Ameaças à validade e limitações metodológicas

- **Otimismo em ROUGE/BLEU:** o teste, embora *held-out* e com agrupamento de paráfrases, compartilha o molde de geração do treino; os ganhos medem sobretudo aderência ao formato institucional (que é o objetivo declarado), não conhecimento clínico geral.
- **Juiz automático:** 60 amostras e um único modelo-juiz; sem avaliação por especialistas humanos.
- **Conteúdo clínico fictício:** protocolos coerentes com diretrizes públicas, porém sem revisão por comissão clínica; o sistema não deve apoiar decisões reais.
- **Anonimização por regras:** robusta aos padrões brasileiros usuais, mas sem NER estatístico; casos atípicos podem escapar (mitigado pela dupla passagem e pelos guardrails de saída).
- **Modelo de 0,5 B:** limitado em raciocínio; a arquitetura compensa com RAG e regras, e permite troca de modelo pelo admin.

## 6. Lições aprendidas

1. **Contrato antes do código** viabilizou paralelismo real (frontend em mock + backend + ML simultâneos) sem retrabalho de integração.
2. **Segurança como código** (guardrails/políticas testáveis) rende evidência objetiva — a mesma função valida produção e avaliação do modelo.
3. **Regras determinísticas antes da LLM** tornam fluxos clínicos auditáveis: a IA explica e sugere; quem decide é o humano; quem alerta é o código.
4. **Fine-tuning pequeno + RAG** supera, para requisitos institucionais (formato, fonte, recusa), um modelo 16× maior sem ajuste — com fração da latência.
5. **Validação de campo cedo** (instalação por terceiros) encontrou classes de erro que testes locais não pegam (DNS em compose, densidade de QR, portas).

## 7. Referências

1. Hu, E. et al. **LoRA: Low-Rank Adaptation of Large Language Models**. arXiv:2106.09685, 2021.
2. Lewis, P. et al. **Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks**. NeurIPS, 2020.
3. Singer, M. et al. **The Third International Consensus Definitions for Sepsis and Septic Shock (Sepsis-3)**. JAMA, 2016. (base do qSOFA)
4. Royal College of Physicians. **National Early Warning Score (NEWS) 2**, 2017.
5. LangChain/LangGraph — documentação oficial (v1.x), 2025.
6. Qwen Team. **Qwen2.5 Technical Report**. arXiv:2412.15115, 2024.
7. OWASP. **Top 10 for Large Language Model Applications**, 2025.
8. Brasil. **Lei nº 13.709/2018 (LGPD)**.
9. Zheng, L. et al. **Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena**. NeurIPS, 2023.
10. Ollama — documentação de importação de modelos (safetensors/GGUF), 2025.

> Conteúdo clínico e dados de pacientes são fictícios/sintéticos; o sistema é acadêmico e não substitui julgamento profissional.
