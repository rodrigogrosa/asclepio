from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..schemas import KnowledgeDocumentDetailOut, KnowledgeDocumentOut, KnowledgeSearchIn
from ..services.knowledge import get_knowledge_service

router = APIRouter(prefix="/knowledge", tags=["base de conhecimento"])


def _doc_out(d, ks) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    return {
        "id": d.id,
        "title": d.title,
        "doc_type": d.doc_type,
        "path": d.path.split("/data/")[-1] if "/data/" in d.path else d.path,
        "version": d.version,
        "category": d.category,
        "tags": d.tags,
        "chunks": ks.chunk_count(d.id),
        "updated_at": d.updated_at,
        "size_chars": d.size_chars,
    }


@router.get(
    "/documents",
    response_model=list[KnowledgeDocumentOut],
    dependencies=[require_permission("knowledge:read")],
)
async def documents(doc_type: str | None = None) -> list[dict[str, Any]]:
    ks = get_knowledge_service()
    docs = [d for d in ks.documents if not doc_type or d.doc_type == doc_type]
    return [_doc_out(d, ks) for d in docs]


@router.get(
    "/documents/{doc_id}",
    response_model=KnowledgeDocumentDetailOut,
    dependencies=[require_permission("knowledge:read")],
)
async def document(doc_id: str) -> dict[str, Any]:
    ks = get_knowledge_service()
    d = ks.document(doc_id)
    if not d:
        raise HTTPException(404, "Documento não encontrado")
    return {**_doc_out(d, ks), "content": d.content}


@router.post("/search", dependencies=[require_permission("knowledge:search")])
async def search(
    body: KnowledgeSearchIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    t0 = time.perf_counter()
    results = await run_in_threadpool(
        get_knowledge_service().search, body.query, body.k, body.doc_type
    )
    ms = int((time.perf_counter() - t0) * 1000)
    await audit.record(
        session,
        action="knowledge.search",
        user=user,
        ip=client_ip(request),
        details={
            "query": body.query[:200],
            "k": body.k,
            "results": [r["source_id"] for r in results],
            "latency_ms": ms,
        },
    )
    return {"results": results, "latency_ms": ms}


@router.post("/reindex", dependencies=[require_permission("knowledge:reindex")])
async def reindex(request: Request, session: DbSession, user: CurrentUser) -> dict[str, Any]:
    res = await run_in_threadpool(get_knowledge_service().ensure_index, True)
    await audit.record(
        session, action="knowledge.reindex", user=user, ip=client_ip(request), details=res
    )
    return res
