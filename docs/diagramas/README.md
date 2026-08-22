# Diagramas

| Arquivo | O que é | Como foi gerado |
|---|---|---|
| `arquitetura.mmd` | Componentes e integrações (Web, API, grafos, RAG, Ollama, LiteLLM, Langfuse) | manual (Mermaid) |
| `grafo_chat_langgraph.mmd` | Grafo do assistente (guard_input → classify_intent → retrieve → generate → guard_output) | `make docs-diagrams` → `graph.get_graph().draw_mermaid()` |
| `grafo_revisao_clinica_langgraph.mmd` | Grafo do fluxo de revisão clínica (10 nós, ramos condicionais, `interrupt`) | `make docs-diagrams` |

Os mesmos grafos são exibidos na UI (`/fluxos`) e expostos pela API (`GET /workflows/graph`, `GET /assistant/graph`).
Diagramas de sequência adicionais estão em `docs/ARQUITETURA.md` e no `docs/RELATORIO_TECNICO.md`.
Renderize `.mmd` no VS Code (extensão Markdown Preview Mermaid) ou em https://mermaid.live.
