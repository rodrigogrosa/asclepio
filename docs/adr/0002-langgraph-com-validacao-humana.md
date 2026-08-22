# ADR-0002: Fluxos como grafos LangGraph com regras determinísticas e `interrupt` para validação humana

- **Status**: aceito · **Data**: 2026-08-21

## Contexto
"Fluxos de decisão automatizados e seguros" que verificam exames pendentes, sugerem tratamentos e emitem alertas — e nunca prescrever sem validação humana.

## Decisão
Modelar a revisão clínica como um **StateGraph** com nós explícitos; risco/alertas calculados por **código** (qSOFA, NEWS2, valores críticos) **antes** da LLM; a LLM apenas sugere/explica com RAG; `interrupt()` pausa em `human_review` (checkpoint SQLite) e a API retoma com `Command(resume=...)`. Cada nó registra um passo (timeline).

## Alternativas
- Agente ReAct livre com tools — menos previsível e difícil de auditar; modelos pequenos (0,5B–8B) falham em tool-calling.
- Pipeline LCEL linear — sem ramificações, sem pausa para humano.

## Consequências
+ Previsível, auditável, explicável; segurança não depende do modelo. + Demonstração clara de LangGraph (ramos condicionais, loop de regeneração, interrupt). − Mais código do que um agente genérico.
