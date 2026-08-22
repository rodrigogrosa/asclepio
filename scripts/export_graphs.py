"""Exporta os grafos LangGraph (Mermaid) para docs/diagramas/ — usados no relatório técnico."""

from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("LLM_PROVIDER", "fake")
os.environ.setdefault("EMBEDDINGS_PROVIDER", "fake")

from asclepio_api.services.assistant import chat_graph_mermaid
from asclepio_api.services.workflow import get_workflow_runtime

out = Path(__file__).resolve().parents[1] / "docs" / "diagramas"
out.mkdir(parents=True, exist_ok=True)
(out / "grafo_chat_langgraph.mmd").write_text(chat_graph_mermaid(), encoding="utf-8")
(out / "grafo_revisao_clinica_langgraph.mmd").write_text(
    get_workflow_runtime().mermaid(), encoding="utf-8"
)
print("grafos exportados em", out)
