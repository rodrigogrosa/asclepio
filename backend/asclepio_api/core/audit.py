"""Serviço de auditoria com cadeia de hashes (tamper-evident).

Cada registro guarda ``prev_hash`` (hash do registro anterior) e ``hash`` =
SHA-256(prev_hash + campos canônicos). Alterar/remover qualquer linha quebra a
cadeia, detectável por ``verify_chain``. É a mesma ideia de um *ledger* simples.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import AuditLog, now_local
from .logging import get_logger, request_id_ctx

log = get_logger("audit")
GENESIS = "0" * 64


def _canonical(
    created_at: datetime,
    user_id: int | None,
    action: str,
    resource_type: str | None,
    resource_id: str | None,
    trace_id: str | None,
    details: dict[str, Any],
) -> str:
    return json.dumps(
        {
            "created_at": created_at.replace(microsecond=0).isoformat(),
            "user_id": user_id,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "trace_id": trace_id,
            "details": details,
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )


def compute_hash(prev_hash: str, canonical: str) -> str:
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


async def record(
    session: AsyncSession,
    *,
    action: str,
    user: Any | None = None,
    resource_type: str | None = None,
    resource_id: str | int | None = None,
    details: dict[str, Any] | None = None,
    ip: str | None = None,
    trace_id: str | None = None,
    commit: bool = True,
) -> AuditLog:
    """Grava um evento de auditoria encadeado ao anterior (ordem garantida por id)."""
    details = _safe_details(details or {})
    trace_id = trace_id or request_id_ctx.get()
    last = (
        await session.execute(select(AuditLog).order_by(AuditLog.id.desc()).limit(1))
    ).scalar_one_or_none()
    prev_hash = last.hash if last else GENESIS
    created_at = now_local().replace(microsecond=0)
    uid = getattr(user, "id", None)
    canonical = _canonical(
        created_at,
        uid,
        action,
        resource_type,
        str(resource_id) if resource_id is not None else None,
        trace_id,
        details,
    )
    entry = AuditLog(
        created_at=created_at,
        user_id=uid,
        user_name=getattr(user, "name", None),
        user_role=getattr(user, "role", None),
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id) if resource_id is not None else None,
        trace_id=trace_id,
        ip=ip,
        details=details,
        prev_hash=prev_hash,
        hash=compute_hash(prev_hash, canonical),
    )
    session.add(entry)
    if commit:
        await session.commit()
    log.info(
        "audit",
        action=action,
        user=getattr(user, "email", None),
        resource=f"{resource_type}:{resource_id}" if resource_type else None,
        **{
            k: v
            for k, v in details.items()
            if k in {"intent", "guardrail_status", "model", "latency_ms", "status", "risk_level"}
        },
    )
    return entry


def _safe_details(d: dict[str, Any]) -> dict[str, Any]:
    """Evita JSON inválido/grande: trunca strings longas e converte tipos exóticos."""
    out: dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, str) and len(v) > 2000:
            out[k] = v[:2000] + "…"
        elif isinstance(v, dict | list | int | float | bool) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


async def verify_chain(session: AsyncSession) -> dict[str, Any]:
    rows = (await session.execute(select(AuditLog).order_by(AuditLog.id))).scalars().all()
    prev = GENESIS
    for r in rows:
        canonical = _canonical(
            r.created_at, r.user_id, r.action, r.resource_type, r.resource_id, r.trace_id, r.details
        )
        if r.prev_hash != prev or compute_hash(prev, canonical) != r.hash:
            return {"ok": False, "checked": len(rows), "broken_at": r.id}
        prev = r.hash
    total = (await session.execute(select(func.count(AuditLog.id)))).scalar_one()
    return {"ok": True, "checked": total, "broken_at": None}
