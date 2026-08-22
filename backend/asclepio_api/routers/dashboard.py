from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.deps import CurrentUser, DbSession, require_permission
from ..core.policies import has_permission
from ..services.dashboard import my_work, stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", dependencies=[require_permission("dashboard:read")])
async def dashboard_stats(session: DbSession, user: CurrentUser) -> dict[str, Any]:
    data = await stats(session)
    if not has_permission(user.role, "model:read"):
        data["model"] = None
    if not has_permission(user.role, "audit:read"):
        data["guardrail_blocks_today"] = None
    data["my_work"] = (
        await my_work(session, user) if user.role in ("medico", "enfermagem", "admin") else None
    )
    return data
