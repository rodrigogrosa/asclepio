# =====================================================================
#  ASCLÉPIO — Makefile (ponto único de entrada; `make help` lista tudo)
# =====================================================================
SHELL := /bin/bash
.DEFAULT_GOAL := help
COMPOSE ?= docker compose
UV ?= uv
NPM ?= npm
PROFILE ?= full

.PHONY: help setup up up-full down logs ps restart clean dev api web install test test-core test-api lint format typecheck \
        seed reindex finetune prepare train export eval eval-quick ollama-create ollama-pull docs-diagrams check ci build pull-images health

help: ## Mostra esta ajuda
	@printf "\n  \033[1;35mASCLÉPIO\033[0m — Assistente Clínico Inteligente (Tech Challenge FIAP · Fase 3)\n\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@printf "\n"

# ---------------------------------------------------------------------
# 🚀 Caminho rápido (tudo em Docker)
# ---------------------------------------------------------------------
setup: ## Instalação automática completa (Docker): verifica pré-requisitos, cria .env, sobe tudo e valida
	@./scripts/bootstrap.sh

up: ## Sobe db + api + web (+ ollama em container se não houver no host)
	@./scripts/bootstrap.sh --no-wait-models

up-full: ## Sobe tudo: + LiteLLM (gateway) + Langfuse (observabilidade LLM)
	@LANGFUSE_ENABLED=true ./scripts/bootstrap.sh --profile observability

down: ## Para e remove containers (mantém volumes)
	$(COMPOSE) --profile ollama --profile gateway --profile observability --profile ml down

clean: down ## Remove containers, volumes e artefatos locais gerados (cuidado: apaga banco/vetores/modelos Ollama do Docker)
	$(COMPOSE) --profile ollama --profile gateway --profile observability --profile ml down -v --remove-orphans
	rm -rf data/vectorstore data/checkpoints data/*.sqlite* frontend/.next

logs: ## Acompanha logs (api e web)
	$(COMPOSE) logs -f api web

ps: ## Lista containers
	$(COMPOSE) --profile ollama --profile gateway --profile observability ps

restart: ## Reinicia api e web
	$(COMPOSE) restart api web

build: ## (Re)constrói as imagens da api e web
	$(COMPOSE) build api web

health: ## Checa saúde da API
	@curl -fsS http://localhost:$${API_PORT:-8000}/health | python3 -m json.tool || (echo "API indisponível"; exit 1)

# ---------------------------------------------------------------------
# 💻 Desenvolvimento local (sem Docker, com hot-reload)
# ---------------------------------------------------------------------
install: ## Instala dependências locais (uv + npm + pre-commit)
	$(UV) sync --all-packages
	cd frontend && $(NPM) install
	-$(UV) run pre-commit install

dev: ## Roda API (8000) e Web (3000) localmente com hot-reload (Ctrl+C encerra ambos)
	@trap 'kill 0' INT; \
	 ( $(MAKE) api ) & ( $(MAKE) web ) & wait

api: ## API local com reload
	$(UV) run uvicorn asclepio_api.main:app --reload --port 8000 --app-dir backend

web: ## Frontend local
	cd frontend && $(NPM) run dev

seed: ## (Re)gera data/synthetic/patients.json
	$(UV) run python -m asclepio_ml synthetic-patients

reindex: ## Reindexa a base de conhecimento via API (exige admin)
	@TOKEN=$$(curl -s -X POST localhost:8000/api/v1/auth/login -H 'content-type: application/json' -d '{"email":"admin@asclepio.fiap","password":"Asclepio@2026"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])'); \
	 curl -s -X POST localhost:8000/api/v1/knowledge/reindex -H "Authorization: Bearer $$TOKEN" | python3 -m json.tool

# ---------------------------------------------------------------------
# ✅ Qualidade
# ---------------------------------------------------------------------
test: test-core test-api ## Roda todos os testes Python
	$(UV) run pytest ml/tests -q

test-core: ## Testes do pacote core
	$(UV) run pytest packages/asclepio_core/tests -q

test-api: ## Testes da API (modo fake, sem Ollama)
	$(UV) run pytest backend/tests -q

lint: ## Lint Python (ruff) + frontend (eslint)
	$(UV) run ruff check .
	$(UV) run ruff format --check .
	cd frontend && $(NPM) run lint

format: ## Formata código Python
	$(UV) run ruff check . --fix
	$(UV) run ruff format .

typecheck: ## Type-check do frontend
	cd frontend && npx tsc --noEmit

check: lint test typecheck ## Tudo que a CI roda

ci: check ## Alias da CI

# ---------------------------------------------------------------------
# 🧠 Machine Learning (fine-tuning) — roda no host (MPS/CUDA); ver ml/README.md
# ---------------------------------------------------------------------
prepare: ## Prepara dataset (anonimização, curadoria, splits, + amostras PubMedQA/MedQuAD) → data/processed/
	$(UV) run python -m asclepio_ml prepare --with-public

prepare-offline: ## Prepara dataset sem baixar datasets públicos (só dados institucionais)
	$(UV) run python -m asclepio_ml prepare

train: ## Fine-tuning LoRA (perfil full) → ml/runs/ + ml/registry.json
	$(UV) run python -m asclepio_ml train --profile $(PROFILE)

export: ## Merge do adapter + criação do modelo `asclepio-med` no Ollama
	$(UV) run python -m asclepio_ml export

eval: ## Avaliação base vs fine-tuned (+ RAG) → ml/reports/eval_latest.json e docs/assets/eval/
	$(UV) run python -m asclepio_ml evaluate

eval-quick: ## Avaliação rápida (poucas amostras)
	$(UV) run python -m asclepio_ml evaluate --max-samples 20

finetune: prepare train export eval docs-metrics ## Pipeline completo de ML (prepare → train → export → eval → docs)

ollama-pull: ## Baixa modelos base no Ollama do host
	ollama pull nomic-embed-text && ollama pull llama3.1:8b

ollama-create: ## (Re)cria o modelo asclepio-med no Ollama a partir de ml/models/asclepio-med/Modelfile
	cd ml/models/asclepio-med && ollama create asclepio-med -f Modelfile

docs-diagrams: ## Exporta os grafos LangGraph (mermaid) para docs/diagramas/
	$(UV) run python scripts/export_graphs.py

docs-metrics: ## Atualiza relatório/README com os números de ml/registry.json e ml/reports/eval_latest.json
	$(UV) run python scripts/update_report_metrics.py
