"""Esquemas do contrato (``docs/CONTRATO_API.md``): ``FinetuneMeta`` e ``EvalReport``.

O backend lê ``ml/registry.json`` e ``ml/reports/eval_latest.json`` e os expõe em
``GET /model/info``; por isso validamos as chaves aqui (e nos testes) — se o esquema
mudar, o teste quebra antes do frontend.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from asclepio_ml.utils import read_json, write_json

FINETUNE_META_FIELDS: tuple[str, ...] = (
    "run_id",
    "base_model",
    "method",
    "trained_at",
    "epochs",
    "train_examples",
    "eval_examples",
    "final_train_loss",
    "final_eval_loss",
    "lora_r",
    "lora_alpha",
    "learning_rate",
    "duration_min",
    "device",
    "ollama_model",
)

EVAL_MODEL_FIELDS: tuple[str, ...] = (
    "rouge_l",
    "bleu",
    "keyword_coverage",
    "citation_rate",
    "judge_score",
    "guardrail_compliance",
    "avg_latency_ms",
    "n",
)
EVAL_RAG_FIELDS: tuple[str, ...] = ("hit_rate_at_5", "mrr", "n_queries")
EVAL_TOP_FIELDS: tuple[str, ...] = ("generated_at", "models", "rag", "per_sample")
EVAL_SAMPLE_FIELDS: tuple[str, ...] = (
    "id",
    "categoria",
    "prompt",
    "reference",
    "outputs",
    "scores",
)


def build_finetune_meta(
    *,
    run_id: str,
    base_model: str,
    epochs: float,
    train_examples: int,
    eval_examples: int,
    final_train_loss: float | None,
    final_eval_loss: float | None,
    lora_r: int,
    lora_alpha: int,
    learning_rate: float,
    duration_min: float,
    device: str,
    ollama_model: str = "asclepio-med",
    trained_at: str | None = None,
    **extras: Any,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "run_id": run_id,
        "base_model": base_model,
        "method": "LoRA",
        "trained_at": trained_at or datetime.now().isoformat(timespec="seconds"),
        "epochs": epochs,
        "train_examples": train_examples,
        "eval_examples": eval_examples,
        "final_train_loss": None if final_train_loss is None else round(float(final_train_loss), 4),
        "final_eval_loss": None if final_eval_loss is None else round(float(final_eval_loss), 4),
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "learning_rate": learning_rate,
        "duration_min": round(float(duration_min), 2),
        "device": device,
        "ollama_model": ollama_model,
    }
    meta.update(extras)
    return meta


def validate_finetune_meta(meta: dict[str, Any]) -> list[str]:
    """Retorna a lista de chaves obrigatórias ausentes (vazia = ok)."""
    return [k for k in FINETUNE_META_FIELDS if k not in meta]


def write_registry(path: str | Path, meta: dict[str, Any]) -> None:
    missing = validate_finetune_meta(meta)
    if missing:
        raise ValueError(f"registry inválido, faltam: {missing}")
    write_json(path, meta)


def read_registry(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return read_json(p)
    except Exception:
        return None


def validate_eval_report(report: dict[str, Any]) -> list[str]:
    """Valida o esquema ``EvalReport``; retorna lista de problemas (vazia = ok)."""
    problems: list[str] = []
    for k in EVAL_TOP_FIELDS:
        if k not in report:
            problems.append(f"top-level sem '{k}'")
    for name, m in (report.get("models") or {}).items():
        for k in EVAL_MODEL_FIELDS:
            if k not in m:
                problems.append(f"models['{name}'] sem '{k}'")
    for k in EVAL_RAG_FIELDS:
        if k not in (report.get("rag") or {}):
            problems.append(f"rag sem '{k}'")
    for i, s in enumerate(report.get("per_sample") or []):
        for k in EVAL_SAMPLE_FIELDS:
            if k not in s:
                problems.append(f"per_sample[{i}] sem '{k}'")
                break
    return problems
