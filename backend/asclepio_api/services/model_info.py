"""Informações do modelo ativo, registro do fine-tuning e relatório de avaliação (lidos do pipeline de ML)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..db import models as m
from .llm import get_llm_factory

ACTIVE_MODEL_KEY = "active_llm_model"


def _read_json(path: str) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


async def load_persisted_model(session: AsyncSession) -> None:
    row = (
        await session.execute(select(m.AppSetting).where(m.AppSetting.key == ACTIVE_MODEL_KEY))
    ).scalar_one_or_none()
    if row:
        get_llm_factory().set_model(row.value)


async def switch_model(session: AsyncSession, name: str) -> dict[str, Any]:
    f = get_llm_factory()
    f.set_model(name)
    row = (
        await session.execute(select(m.AppSetting).where(m.AppSetting.key == ACTIVE_MODEL_KEY))
    ).scalar_one_or_none()
    if row:
        row.value = name
    else:
        session.add(m.AppSetting(key=ACTIVE_MODEL_KEY, value=name))
    await session.commit()
    return f.resolve_model().as_dict()


def model_overview() -> dict[str, Any]:
    s = get_settings()
    f = get_llm_factory()
    active = f.resolve_model().as_dict()
    available: list[dict[str, Any]] = []
    if s.llm_provider == "ollama":
        available = [
            {
                "name": mm["name"],
                "fine_tuned": mm["name"].startswith("asclepio-med"),
                "size": mm.get("size", 0),
            }
            for mm in f.ollama_models(refresh=True)
        ]
    elif s.llm_provider == "fake":
        available = [{"name": "fake-clinical", "fine_tuned": False, "size": 0}]
    else:
        available = [
            {"name": s.llm_model, "fine_tuned": s.llm_model.startswith("asclepio-med"), "size": 0},
            {"name": s.llm_fallback_model, "fine_tuned": False, "size": 0},
        ]
    emb = (
        f.embeddings()[1]
        if s.embeddings_provider != "ollama"
        else {"provider": "ollama", "model": s.embeddings_model}
    )
    return {
        "active": active,
        "available": available,
        "finetune": _read_json(s.ml_registry_file),
        "evaluation": _read_json(s.ml_eval_report_file),
        "embeddings": emb,
    }
