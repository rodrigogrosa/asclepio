from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..schemas import ExamOut, PatientContextOut, PatientDetailOut, PatientOut
from ..services.patients import (
    build_context,
    detail,
    get_patient,
    list_patients,
    professional_names,
    summarize,
)

router = APIRouter(prefix="/patients", tags=["pacientes"])


@router.get("", response_model=list[PatientOut], dependencies=[require_permission("patients:read")])
async def patients(
    session: DbSession, search: str | None = None, ward: str | None = None, risk: str | None = None
) -> list[dict]:
    rows = [summarize(p) for p in await list_patients(session, search, ward)]
    if risk:
        rows = [r for r in rows if r["risk_level"] == risk]
    order = {"critico": 0, "alto": 1, "moderado": 2, "baixo": 3}
    return sorted(rows, key=lambda r: (order[r["risk_level"]], r["ward"], r["bed"]))


@router.get(
    "/{patient_id}",
    response_model=PatientDetailOut,
    dependencies=[require_permission("patients:read")],
)
async def patient_detail(
    patient_id: int, request: Request, session: DbSession, user: CurrentUser
) -> dict:
    p = await get_patient(session, patient_id)
    if not p:
        raise HTTPException(404, "Paciente não encontrado")
    await audit.record(
        session,
        action="patient.view",
        user=user,
        resource_type="patient",
        resource_id=patient_id,
        ip=client_ip(request),
        details={"mrn": p.mrn},
    )
    return detail(p)


@router.get(
    "/{patient_id}/pending-exams",
    response_model=list[ExamOut],
    dependencies=[require_permission("patients:read")],
)
async def pending_exams(patient_id: int, session: DbSession) -> list:
    p = await get_patient(session, patient_id)
    if not p:
        raise HTTPException(404, "Paciente não encontrado")
    return [e for e in detail(p)["exams"] if e["status"] in ("pendente", "coletado", "atrasado")]


@router.get(
    "/{patient_id}/context",
    response_model=PatientContextOut,
    dependencies=[require_permission("patients:context")],
)
async def patient_context(patient_id: int, session: DbSession) -> dict:
    p = await get_patient(session, patient_id)
    if not p:
        raise HTTPException(404, "Paciente não encontrado")
    ctx, _risk, pii = build_context(p, await professional_names(session))
    return {"anonymized_context": ctx, "pii_redacted": sum(pii.values()), "pii_by_type": pii}
