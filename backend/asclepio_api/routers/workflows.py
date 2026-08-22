from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..db import models as m
from ..schemas import WorkflowDecisionIn, WorkflowRunOut, WorkflowStartIn
from ..services.workflow import NODE_DESCRIPTIONS, NODE_LABELS, get_workflow_runtime, run_to_dict

router = APIRouter(prefix="/workflows", tags=["fluxos"])


async def _name(session, pid: int) -> str:  # type: ignore[no-untyped-def]
    return (
        await session.execute(select(m.Patient.name).where(m.Patient.id == pid))
    ).scalar_one_or_none() or ""


@router.post(
    "/clinical-review",
    response_model=WorkflowRunOut,
    dependencies=[require_permission("workflows:run")],
)
async def start_review(
    body: WorkflowStartIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    from ..core.logging import request_id_ctx

    try:
        run = await get_workflow_runtime().start_run(
            session,
            user=user,
            patient_id=body.patient_id,
            reason=body.reason,
            trace_id=request_id_ctx.get(),
            ip=client_ip(request),
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return run_to_dict(run, await _name(session, run.patient_id))


@router.post(
    "/runs/{run_id}/decision",
    response_model=WorkflowRunOut,
    dependencies=[require_permission("workflows:decide")],
)
async def decide(
    run_id: str, body: WorkflowDecisionIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    run = (
        await session.execute(select(m.WorkflowRun).where(m.WorkflowRun.run_id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    if run.status != "aguardando_aprovacao":
        raise HTTPException(
            409, f"Execução não está aguardando aprovação (status atual: {run.status})"
        )
    run = await get_workflow_runtime().decide(
        session,
        run=run,
        user=user,
        approved=body.approved,
        comment=body.comment,
        ip=client_ip(request),
    )
    return run_to_dict(run, await _name(session, run.patient_id))


@router.get(
    "/runs",
    response_model=list[WorkflowRunOut],
    dependencies=[require_permission("workflows:read")],
)
async def runs(
    session: DbSession, patient_id: int | None = None, status: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    q = select(m.WorkflowRun).order_by(m.WorkflowRun.started_at.desc()).limit(min(limit, 200))
    if patient_id:
        q = q.where(m.WorkflowRun.patient_id == patient_id)
    if status:
        q = q.where(m.WorkflowRun.status == status)
    rows = (await session.execute(q)).scalars().all()
    names = dict((await session.execute(select(m.Patient.id, m.Patient.name))).all())
    return [run_to_dict(r, names.get(r.patient_id, "")) for r in rows]


@router.get("/graph", dependencies=[require_permission("system:internals")])
async def graph() -> dict[str, Any]:
    return {
        "mermaid": get_workflow_runtime().mermaid(),
        "nodes": [
            {"id": k, "label": v, "description": NODE_DESCRIPTIONS.get(k, "")}
            for k, v in NODE_LABELS.items()
        ],
    }


@router.get(
    "/runs/{run_id}",
    response_model=WorkflowRunOut,
    dependencies=[require_permission("workflows:read")],
)
async def run_detail(run_id: str, session: DbSession) -> dict[str, Any]:
    run = (
        await session.execute(select(m.WorkflowRun).where(m.WorkflowRun.run_id == run_id))
    ).scalar_one_or_none()
    if not run:
        raise HTTPException(404, "Execução não encontrada")
    return run_to_dict(run, await _name(session, run.patient_id))
