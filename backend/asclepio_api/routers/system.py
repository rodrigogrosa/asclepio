from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from ..core.config import get_settings
from ..core.deps import DbSession
from ..services.knowledge import get_knowledge_service
from ..services.llm import get_llm_factory

router = APIRouter(tags=["sistema"])


@router.get("/health")
async def health(session: DbSession) -> dict[str, Any]:
    s = get_settings()
    f = get_llm_factory()
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    reachable = s.llm_provider == "fake" or (
        await run_in_threadpool(f.ollama_reachable) if s.llm_provider == "ollama" else True
    )
    info = f.resolve_model()
    chunks = await run_in_threadpool(get_knowledge_service().index_count)
    status = "ok" if (db_ok and reachable and chunks > 0) else "degraded"
    return {
        "status": status,
        "version": s.app_version,
        "env": s.app_env,
        "llm": {
            "provider": info.provider,
            "model": info.name,
            "fine_tuned": info.fine_tuned,
            "reachable": reachable,
        },
        "embeddings": {"provider": s.embeddings_provider, "model": s.embeddings_model},
        "db": "ok" if db_ok else "error",
        "vectorstore": {"chunks": chunks},
        "langfuse": s.langfuse_active,
    }
