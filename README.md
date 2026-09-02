<p align="center">
  <img src="docs/assets/brand/asclepio-logo-horizontal.svg" alt="Asclépio — Assistente Clínico Inteligente" width="720">
</p>

<p align="center">
  <b>Assistente clínico com inteligência artificial treinada com os protocolos do hospital.</b><br>
  Responde dúvidas da equipe médica citando as fontes, executa revisões clínicas automatizadas com validação humana e registra tudo em auditoria.<br>
  <i>Projeto do Tech Challenge · FIAP Pós-Tech IA para Devs (8IADT) · Fase 3</i>
</p>

---

# 🚀 Como rodar na sua máquina (passo a passo)

> **Não precisa saber programar.** São 3 instalações com o mouse + 1 comando para colar no terminal. Tempo total: 15–30 min (a maior parte é download). Tudo gratuito, nada é enviado para a internet.

### Passo 1 — Instale o Docker Desktop *(obrigatório)*
É o programa que roda o sistema. Baixe, instale e **deixe aberto** (ícone de baleia na barra):
- **Mac**: https://docs.docker.com/desktop/setup/install/mac-install/ → baixe o arquivo `.dmg` (escolha *Apple Silicon* para Macs com chip M1/M2/M3/M4), arraste para Aplicativos, abra e aceite os termos.
- **Windows**: https://docs.docker.com/desktop/setup/install/windows-install/ → baixe o `.exe`, instale (aceite ativar o WSL 2 se ele pedir), reinicie o computador e abra o Docker Desktop.
- **Linux (Ubuntu)**: o comando do Passo 3 instala sozinho — pule este passo.

### Passo 2 — Instale o Ollama *(recomendado — deixa a IA rápida)*
É o programa que roda os modelos de IA localmente: https://ollama.com/download → baixe, instale e abra uma vez. *(Se pular este passo, funciona mesmo assim, só que mais lento.)*

### Passo 3 — Abra o terminal e cole o comando do seu sistema

**🍎 macOS** — aperte `Cmd + barra de espaço`, digite `Terminal`, Enter. Cole e aperte Enter:
```bash
curl -fsSL https://raw.githubusercontent.com/rodrigogrosa/asclepio/main/install.sh | bash
```

**🪟 Windows** — são 2 momentos:
1. Menu Iniciar → digite `PowerShell` → botão direito → **Executar como administrador** → cole (só na 1ª vez; reinicie se pedir):
```powershell
wsl --install
```
2. Menu Iniciar → digite `Ubuntu` → abra (na 1ª vez ele cria um usuário) → cole no terminal do Ubuntu:
```bash
curl -fsSL https://raw.githubusercontent.com/rodrigogrosa/asclepio/main/install.sh | bash
```

**🐧 Linux (Ubuntu/Debian)** — aperte `Ctrl + Alt + T` e cole (vai pedir sua senha para instalar o Docker):
```bash
curl -fsSL https://raw.githubusercontent.com/rodrigogrosa/asclepio/main/install.sh | bash
```

Espere terminar (aparece **"Tudo pronto!"** com os endereços e as senhas). ☕
> 💡 No Windows, **todos os comandos deste projeto** (`make up`, `make down`, `grep ASCLEPIO_ .env`…) são digitados no terminal do **Ubuntu**, não no PowerShell.

### Passo 4 — Use o sistema
Abra o navegador em **http://localhost:3000** e entre:

| Quero ver… | Entre com | Senha |
|---|---|---|
| A visão do **médico** (pacientes, assistente de IA, revisões clínicas, alertas) | `dra.ana@asclepio.fiap` | `Asclepio@2026` |
| A visão da **enfermagem** | `enf.carla@asclepio.fiap` | `Asclepio@2026` |
| A **auditoria** e a **Documentação** do projeto | `auditor@asclepio.fiap` | `Asclepio@2026` |
| **Tudo** (administração, IA & Modelos, usuários, documentação) | `admin@asclepio.fiap` | apareceu no final da instalação* |

\* Perdeu a senha do admin? No mesmo terminal, dentro da pasta do projeto (`cd ~/asclepio`), rode `grep ASCLEPIO_ .env` — ela aparece. No 1º acesso o admin troca a senha e cadastra um **aplicativo autenticador** (Google Authenticator etc.) escaneando um QR code — o próprio sistema ensina.

### O que testar primeiro (5 minutos)
1. **Assistente** → pergunte: *"Qual o alvo de lactato na reavaliação segundo o protocolo de sepse?"* → veja a resposta com as **fontes**.
2. Ainda no Assistente → selecione um paciente → **"ver contexto anonimizado"** (o que a IA recebe, sem dados pessoais).
3. **Pacientes** → abra o primeiro paciente (crítico) → **"Executar revisão clínica"** → acompanhe as etapas → **Aprovar**.
4. Peça algo proibido: *"Prescreva 2 g de ceftriaxona para o leito 5"* → a IA **recusa** (nunca prescreve).
5. Como auditor/admin → **Documentação**: todos os relatórios e evidências do projeto, para ler e baixar.

### Deu errado? Os 3 problemas mais comuns
| O que apareceu | O que fazer |
|---|---|
| "Docker não está em execução" | Abra o Docker Desktop, espere a baleia parar de se mexer e rode o comando de novo |
| "port is already allocated" (porta ocupada) | Algum programa seu já usa a porta. Abra o arquivo `~/asclepio/.env`, troque `WEB_PORT=3000` por `WEB_PORT=3005` (e/ou `API_PORT=8000`→`8005`) e rode `cd ~/asclepio && make up` |
| Chat diz "serviço de modelos de IA indisponível" | Rode `cd ~/asclepio && make up` (ele conserta sozinho) |

Guia completo com mais detalhes e problemas: **[docs/GUIA_INSTALACAO.md](docs/GUIA_INSTALACAO.md)** (também em [PDF](docs/GUIA_INSTALACAO.pdf)). Para **parar** o sistema: `cd ~/asclepio && make down`.

---

# 🩺 O que é o Asclépio

- **Assistente de IA treinado com os dados do hospital** (fictício): fizemos *fine-tuning* de um modelo de linguagem com 16 protocolos clínicos, 10 modelos de documentos e 167 perguntas frequentes — ele responde no formato institucional, **cita as fontes** e **nunca prescreve** sem validação humana.
- **Fluxos clínicos automatizados e seguros**: ao revisar um paciente, o sistema verifica exames pendentes, calcula risco (qSOFA/NEWS2), consulta os protocolos, sugere condutas com fontes, emite alertas — e **pausa para um médico aprovar**.
- **Seguro e auditável**: dados de pacientes são anonimizados antes de chegar à IA; login com autenticação em duas etapas; cada perfil vê só o que deve; toda ação fica numa trilha de auditoria imutável.
- **100 % local e gratuito**: os modelos rodam na sua máquina (Ollama); nenhum dado sai do computador.

Resultado do treinamento (medido, não prometido): o modelo ajustado ficou ~3× melhor em aderência ao formato institucional (ROUGE-L 0,13 → 0,36), obedece aos limites de segurança em 95 % dos casos (antes 77 %) e responde em ~1 s. Detalhes em [docs/FINE_TUNING.md](docs/FINE_TUNING.md).

# 📚 Para avaliadores e curiosos (documentação completa)

**Dentro do próprio sistema**: menu **Documentação** (perfil admin ou auditor) — todos os artefatos para ler e baixar.

| Documento | O que tem |
|---|---|
| [Guia de instalação](docs/GUIA_INSTALACAO.md) · [PDF](docs/GUIA_INSTALACAO.pdf) | Passo a passo detalhado por sistema operacional + problemas comuns |
| [Relatório técnico](docs/RELATORIO_TECNICO.md) · [PDF](docs/RELATORIO_TECNICO.pdf) | Documento central da entrega (34 págs.): dados, fine-tuning, assistente, fluxos, segurança, avaliação |
| [Processo de desenvolvimento](docs/PROCESSO_DESENVOLVIMENTO.md) | Como foi feito, etapa por etapa (visão acadêmica) |
| [Mapa de evidências](docs/EVIDENCIAS.md) | Onde cada exigência do edital aparece no sistema |
| [Arquitetura](docs/ARQUITETURA.md) · [ADRs](docs/adr/) · [Contrato da API](docs/CONTRATO_API.md) | Desenho da solução e decisões |
| [Fine-tuning](docs/FINE_TUNING.md) · [Dataset card](data/processed/DATASET_CARD.md) | Treinamento e avaliação do modelo, com números reais |
| [Políticas de segurança](docs/POLITICAS.md) | MFA, perfis de acesso, LGPD, guardrails, auditoria |
| [Roteiro do vídeo](docs/ROTEIRO_VIDEO.md) | Cena a cena da demonstração (≤ 15 min) |

<details>
<summary><b>🔧 Para desenvolvedores</b> — comandos, estrutura do código, testes e stack (clique para abrir)</summary>

### Comandos principais (`make help` lista todos)
```bash
make setup      # instala e sobe tudo em Docker (o que o install.sh chama)
make up-full    # + LiteLLM (gateway) e Langfuse (observabilidade de LLM)
make dev        # desenvolvimento local com hot-reload (requer: uv, node)
make check      # lint + 88 testes + typecheck (o que a CI roda)
make finetune   # reproduz o fine-tuning: prepare → train (LoRA) → export → eval
make docs-pdf   # regenera os PDFs do relatório e do guia
make down       # para tudo · make clean remove tudo
```

### Estrutura
```
packages/asclepio_core/  # anonimização (LGPD), regras clínicas, guardrails, base de conhecimento, dados sintéticos
backend/                 # FastAPI + LangChain/LangGraph (auth MFA, pacientes, assistente, fluxos, auditoria, docs-hub)
frontend/                # Next.js 16 (identidade FIAP), navegação por permissão, modo mock
ml/                      # pipeline de fine-tuning: prepare → train → export → evaluate
data/                    # knowledge_base (protocolos/FAQ/modelos) · synthetic · processed (dataset SFT)
docs/                    # relatórios, ADRs, diagramas, políticas, guias
infra/ · scripts/        # LiteLLM, Ollama init, Postgres, bootstrap, geradores de PDF/métricas
```

### Stack e garantias
Python 3.12 (uv) · LangChain/LangGraph 1.x · Transformers/PEFT/TRL · Ollama · ChromaDB · FastAPI · SQLAlchemy 2 · PostgreSQL · Next.js 16/React 19/Tailwind 4 · Docker Compose · GitHub Actions (lint, 88 testes, build, gitleaks/pip-audit) · pre-commit · Dev Container. O modelo fine-tunado (`asclepio-med`) é baixado automaticamente da [Release v1.2.0](https://github.com/rodrigogrosa/asclepio/releases/tag/v1.2.0). Provedores de LLM plugáveis (`ollama` | `litellm` | `openai` | `fake` para CI). Segredos só via `.env`; senhas de admin geradas por instalação.

Contribuições: [CONTRIBUTING.md](CONTRIBUTING.md) · Segurança: [SECURITY.md](SECURITY.md) · Histórico: [CHANGELOG.md](CHANGELOG.md)
</details>

## ⚠️ Aviso
Projeto **acadêmico**: protocolos, pacientes e dados são **fictícios/sintéticos**. O Asclépio não prescreve e não deve apoiar decisões clínicas reais.

## 📄 Licença
MIT — [LICENSE](LICENSE).
