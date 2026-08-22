from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.deps import DbSession, require_permission
from ..services.dashboard import stats

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", dependencies=[require_permission("dashboard:read")])
async def dashboard_stats(session: DbSession) -> dict[str, Any]:
    return await stats(session)
