from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..schemas import AlertOut
from ..services.alerts import ack_alert, list_alerts
from ..services.patients import alert_dict

router = APIRouter(prefix="/alerts", tags=["alertas"])


@router.get("", response_model=list[AlertOut], dependencies=[require_permission("alerts:read")])
async def alerts(
    session: DbSession,
    patient_id: int | None = None,
    severity: str | None = None,
    open_only: bool = True,
) -> list[dict[str, Any]]:
    rows = await list_alerts(session, patient_id, severity, open_only)
    return [alert_dict(a, a.patient.name if a.patient else "") for a in rows]


@router.post(
    "/{alert_id}/ack", response_model=AlertOut, dependencies=[require_permission("alerts:ack")]
)
async def ack(
    alert_id: int, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    a = await ack_alert(session, alert_id, user.name)
    if not a:
        raise HTTPException(404, "Alerta não encontrado")
    await audit.record(
        session,
        action="alert.ack",
        user=user,
        resource_type="alert",
        resource_id=alert_id,
        ip=client_ip(request),
        details={"title": a.title, "patient_id": a.patient_id},
    )
    return alert_dict(a, a.patient.name if a.patient else "")
