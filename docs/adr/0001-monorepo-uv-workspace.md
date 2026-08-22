# ADR-0001: Monorepo com workspace `uv` (core + backend + ml) e frontend Next.js

- **Status**: aceito · **Data**: 2026-08-21

## Contexto
O desafio exige "projeto modularizado em Python" com fine-tuning, LangChain/LangGraph e README completo. Queremos que ML e produto compartilhem código (anonimização, guardrails, regras clínicas) sem duplicação, e que um único comando instale tudo.

## Decisão
Monorepo com **uv workspace**: `packages/asclepio_core` (biblioteca pura), `backend` (API) e `ml` (pipeline) como membros; um `uv.lock` e um `.venv`. Frontend separado em `frontend/` (npm). `Makefile` como ponto de entrada.

## Alternativas
- Repositórios separados — mais atrito para manter contratos e compartilhar código.
- Poetry/pip-tools — mais lentos; uv resolve workspace nativamente e instala em segundos.

## Consequências
+ Mesmo código de guardrails/anonimização em ML e API (consistência entre avaliação e produto). + `uv sync --all-packages` instala tudo. − torch entra no lock (instalação pesada) — mitigado com `--package asclepio-api` no Dockerfile da API.
