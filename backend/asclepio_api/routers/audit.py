from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from sqlalchemy import String, cast, func, select

from ..core import audit as audit_svc
from ..core.deps import CurrentUser, DbSession, require_permission
from ..db import models as m
from ..schemas import AuditEntryOut, AuditPageOut

router = APIRouter(prefix="/audit", tags=["auditoria"])


@router.get("", response_model=AuditPageOut, dependencies=[require_permission("audit:read")])
async def list_audit(
    session: DbSession,
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    user_id: int | None = None,
    q: str | None = None,
) -> dict[str, Any]:
    base = select(m.AuditLog)
    if action:
        base = base.where(m.AuditLog.action == action)
    if user_id:
        base = base.where(m.AuditLog.user_id == user_id)
    if q:
        like = f"%{q}%"
        base = base.where(
            (m.AuditLog.user_name.ilike(like))
            | (m.AuditLog.resource_id.ilike(like))
            | (m.AuditLog.trace_id.ilike(like))
            | (cast(m.AuditLog.details, String).ilike(like))
        )
    total = (await session.execute(select(func.count()).select_from(base.subquery()))).scalar_one()
    rows = (
        (
            await session.execute(
                base.order_by(m.AuditLog.id.desc()).offset(offset).limit(min(limit, 200))
            )
        )
        .scalars()
        .all()
    )
    return {"items": rows, "total": total}


@router.get("/verify", dependencies=[require_permission("audit:read")])
async def verify(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    res = await audit_svc.verify_chain(session)
    await audit_svc.record(session, action="audit.verify", user=user, details=res)
    return res


@router.get("/actions", dependencies=[require_permission("audit:read")])
async def actions(session: DbSession) -> list[str]:
    rows = (
        (await session.execute(select(m.AuditLog.action).distinct().order_by(m.AuditLog.action)))
        .scalars()
        .all()
    )
    return list(rows)


@router.get(
    "/{entry_id}", response_model=AuditEntryOut, dependencies=[require_permission("audit:read")]
)
async def entry(entry_id: int, session: DbSession) -> m.AuditLog:
    row = (
        await session.execute(select(m.AuditLog).where(m.AuditLog.id == entry_id))
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(404, "Registro não encontrado")
    return row
