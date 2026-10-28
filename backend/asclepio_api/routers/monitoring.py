"""Monitoramento multimodal (Fase 4): vídeo, áudio, séries do prontuário, fusão e monitor ao vivo.
Contrato em docs/CONTRATO_API.md, seção "Monitoramento multimodal"."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sse_starlette.sse import EventSourceResponse

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..db import models as m
from ..schemas import AnalysisOut, AnalysisSummaryOut, LiveStartIn
from ..services import monitoring as svc
from ..services.events import bus

router = APIRouter(prefix="/monitoring", tags=["monitoramento multimodal"])


async def _patient_name(session, pid: int) -> str:  # type: ignore[no-untyped-def]
    return (
        await session.execute(select(m.Patient.name).where(m.Patient.id == pid))
    ).scalar_one_or_none() or ""


async def _get(session, analysis_id: str) -> m.MonitoringAnalysis:  # type: ignore[no-untyped-def]
    row = await session.get(m.MonitoringAnalysis, analysis_id)
    if row is None:
        raise HTTPException(404, "Análise não encontrada")
    return row


@router.get("/status", dependencies=[require_permission("monitoring:read")])
async def status() -> dict[str, Any]:
    return svc.status()


@router.post(
    "/analyses",
    status_code=202,
    response_model=AnalysisSummaryOut,
    dependencies=[require_permission("monitoring:run")],
)
async def create_analysis(
    request: Request,
    session: DbSession,
    user: CurrentUser,
    kind: str = Form(...),
    patient_id: int = Form(...),
    file: UploadFile | None = File(None),
    sample: str | None = Form(None),
    profile: str | None = Form(None),
    exercise: str | None = Form(None),
) -> dict[str, Any]:
    row = await svc.create_media_analysis(
        session,
        user=user,
        patient_id=patient_id,
        kind=kind,
        upload=file,
        sample=sample or None,
        profile=profile or None,
        exercise=exercise or None,
        ip=client_ip(request),
    )
    return svc.summary_dict(row, await _patient_name(session, patient_id))


@router.get(
    "/analyses",
    response_model=list[AnalysisSummaryOut],
    dependencies=[require_permission("monitoring:read")],
)
async def list_analyses(
    session: DbSession, patient_id: int | None = None, kind: str | None = None, limit: int = 50
) -> list[dict[str, Any]]:
    q = (
        select(m.MonitoringAnalysis)
        .order_by(m.MonitoringAnalysis.created_at.desc())
        .limit(min(max(limit, 1), 200))
    )
    if patient_id:
        q = q.where(m.MonitoringAnalysis.patient_id == patient_id)
    if kind:
        q = q.where(m.MonitoringAnalysis.kind == kind)
    rows = (await session.execute(q)).scalars().all()
    names = dict((await session.execute(select(m.Patient.id, m.Patient.name))).all())
    return [svc.summary_dict(r, names.get(r.patient_id, "")) for r in rows]


@router.get(
    "/analyses/{analysis_id}",
    response_model=AnalysisOut,
    dependencies=[require_permission("monitoring:read")],
)
async def get_analysis(
    analysis_id: str, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    row = await _get(session, analysis_id)
    if row.status == "concluida" and row.kind in ("video", "audio"):
        # mídia de paciente é dado sensível: quem abriu o resultado fica registrado
        await audit.record(
            session,
            action="monitoring.analysis.view",
            user=user,
            resource_type="monitoring_analysis",
            resource_id=analysis_id,
            ip=client_ip(request),
            details={"patient_id": row.patient_id, "kind": row.kind},
        )
    return svc.detail_dict(row, await _patient_name(session, row.patient_id))


@router.get(
    "/analyses/{analysis_id}/artifacts/{name}",
    dependencies=[require_permission("monitoring:read")],
)
async def get_artifact(analysis_id: str, name: str, session: DbSession) -> FileResponse:
    row = await _get(session, analysis_id)
    p = svc.artifact_path(row, name)
    if p is None:
        raise HTTPException(404, "Artefato não encontrado")
    return FileResponse(p, media_type=svc.content_type(p), filename=p.name)


@router.get("/patients/{patient_id}", dependencies=[require_permission("monitoring:read")])
async def patient_monitoring(patient_id: int, session: DbSession) -> dict[str, Any]:
    return await svc.overview(session, patient_id)


@router.post("/patients/{patient_id}/scan", dependencies=[require_permission("monitoring:run")])
async def scan(
    patient_id: int, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    return await svc.scan_patient(session, patient_id=patient_id, user=user, ip=client_ip(request))


@router.post("/live/start", dependencies=[require_permission("monitoring:run")])
async def live_start(
    body: LiveStartIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    return await svc.start_live(
        session,
        user=user,
        patient_id=body.patient_id,
        source=body.source,
        speed=body.speed,
        ip=client_ip(request),
    )


@router.post("/live/{session_id}/stop", dependencies=[require_permission("monitoring:run")])
async def live_stop(
    session_id: str, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    stopped = await svc.stop_live(session_id)
    if not stopped:
        raise HTTPException(404, "Sessão ao vivo não encontrada ou já encerrada")
    await audit.record(
        session,
        action="monitoring.live.stop",
        user=user,
        resource_type="monitoring_analysis",
        resource_id=session_id,
        ip=client_ip(request),
    )
    return {"stopped": True, "session_id": session_id}


@router.get("/live/stream", dependencies=[require_permission("monitoring:read")])
async def live_stream(patient_id: int) -> EventSourceResponse:
    """SSE: vital · finding · alert · end (o alerta chega também pelo /alerts/stream)."""

    async def gen():  # type: ignore[no-untyped-def]
        async with bus.subscribe(f"live:{patient_id}") as q:
            yield {"event": "ready", "data": json.dumps({"patient_id": patient_id})}
            while True:
                event, data = await q.get()
                yield {"event": event, "data": json.dumps(data, default=str)}

    return EventSourceResponse(gen(), ping=15)
