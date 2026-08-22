from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from starlette.concurrency import run_in_threadpool

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..schemas import ModelSwitchIn
from ..services.model_info import model_overview, switch_model

router = APIRouter(prefix="/model", tags=["modelo"])


@router.get("/info", dependencies=[require_permission("model:read")])
async def info() -> dict[str, Any]:
    return await run_in_threadpool(model_overview)


@router.post("/switch", dependencies=[require_permission("model:switch")])
async def switch(
    body: ModelSwitchIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    active = await switch_model(session, body.model)
    await audit.record(
        session,
        action="model.switch",
        user=user,
        ip=client_ip(request),
        details={"requested": body.model, "active": active},
    )
    return {"active": active}
