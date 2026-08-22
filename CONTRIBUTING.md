# Contribuindo com o Asclépio

Obrigado por contribuir! Este projeto segue um padrão de **Developer Experience (DevEx)** simples e previsível.

## Fluxo de trabalho
1. `make install` (dependências + hooks do pre-commit) ou abra no **Dev Container**.
2. Crie uma branch a partir de `main`: `feat/<tema>`, `fix/<tema>`, `docs/<tema>`.
3. Commits no padrão **Conventional Commits** (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`), em português ou inglês.
4. Antes do push: `make check` (ruff + pytest + eslint + tsc). O `pre-commit` já roda ruff/gitleaks a cada commit.
5. Abra um PR usando o template. A CI (`.github/workflows/ci.yml`) precisa estar verde.

## Estrutura
| Pasta | O que é |
|---|---|
| `packages/asclepio_core` | núcleo compartilhado (anonimização, regras clínicas, guardrails, base de conhecimento, dados sintéticos) |
| `backend` | API FastAPI + LangChain/LangGraph |
| `frontend` | Next.js (App Router, Tailwind) |
| `ml` | pipeline de fine-tuning/avaliação |
| `data` | base de conhecimento, dados sintéticos, dataset processado |
| `docs` | relatório técnico, ADRs, diagramas, identidade visual |
| `infra` | configs de LiteLLM, Ollama, Postgres |

## Decisões de arquitetura
Registre decisões relevantes em `docs/adr/` (use `docs/adr/0000-template.md`).

## Código
- Python: `ruff` (lint + format), type hints, docstrings em pt-BR explicando o **porquê**.
- Frontend: TypeScript estrito, componentes em `components/ui`, textos em pt-BR.
- Testes: `backend/tests` roda com `LLM_PROVIDER=fake` (sem rede). Novos endpoints precisam de teste.
- Nunca commite segredos (`gitleaks` bloqueia) nem dados reais de pacientes — só sintéticos.
