"""Consultas de pacientes + construção do contexto clínico **anonimizado** para a LLM."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from asclepio_core.anonymizer import Anonymizer
from asclepio_core.clinical_rules import RiskAssessment, assess_risk, is_overdue
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from ..db import models as m


def _d(dt: datetime | None) -> str:
    return dt.strftime("%d/%m %H:%M") if dt else "-"


async def list_patients(
    session: AsyncSession, search: str | None = None, ward: str | None = None
) -> list[m.Patient]:
    q = (
        select(m.Patient)
        .options(
            selectinload(m.Patient.exams),
            selectinload(m.Patient.vitals),
            selectinload(m.Patient.alerts),
        )
        .order_by(m.Patient.ward, m.Patient.bed)
    )
    if search:
        like = f"%{search.lower()}%"
        q = q.where(
            (m.Patient.name.ilike(like))
            | (m.Patient.mrn.ilike(like))
            | (m.Patient.primary_diagnosis.ilike(like))
        )
    if ward:
        q = q.where(m.Patient.ward == ward)
    return list((await session.execute(q)).scalars().unique().all())


async def get_patient(session: AsyncSession, patient_id: int) -> m.Patient | None:
    q = (
        select(m.Patient)
        .where(m.Patient.id == patient_id)
        .options(
            selectinload(m.Patient.exams),
            selectinload(m.Patient.vitals),
            selectinload(m.Patient.medications),
            selectinload(m.Patient.notes),
            selectinload(m.Patient.alerts),
        )
    )
    return (await session.execute(q)).scalars().unique().one_or_none()


def exam_dicts(p: m.Patient) -> list[dict[str, Any]]:
    return [
        {
            "id": e.id,
            "name": e.name,
            "status": e.status,
            "result_value": e.result_value,
            "unit": e.unit,
            "due_at": e.due_at,
            "requested_at": e.requested_at,
            "category": e.category,
            "note": e.note,
            "reference_range": e.reference_range,
            "is_critical": e.is_critical,
        }
        for e in p.exams
    ]


def latest_vital(p: m.Patient) -> dict[str, Any] | None:
    if not p.vitals:
        return None
    v = max(p.vitals, key=lambda x: x.measured_at)
    return {
        "measured_at": v.measured_at,
        "hr": v.hr,
        "sbp": v.sbp,
        "dbp": v.dbp,
        "rr": v.rr,
        "temp_c": v.temp_c,
        "spo2": v.spo2,
        "gcs": v.gcs,
    }


def risk_for(p: m.Patient, now: datetime | None = None) -> RiskAssessment:
    dx_text = (
        " ".join([p.primary_diagnosis, *p.comorbidities, *[n.text for n in (p.notes or [])][-3:]])
        if getattr(p, "notes", None)
        else p.primary_diagnosis
    )
    return assess_risk(latest_vital(p), exam_dicts(p), dx_text, p.age, now)


def summarize(p: m.Patient, now: datetime | None = None) -> dict[str, Any]:
    """Resumo para a listagem (inclui risco calculado em tempo real)."""
    now = now or datetime.now()
    exams = exam_dicts(p)
    pending = [e for e in exams if e["status"] in ("pendente", "coletado", "atrasado")]
    overdue = [e for e in exams if is_overdue(e, now)]
    risk = assess_risk(latest_vital(p), exams, p.primary_diagnosis, p.age, now)
    return {
        "id": p.id,
        "mrn": p.mrn,
        "name": p.name,
        "birth_date": p.birth_date,
        "age": p.age,
        "sex": p.sex,
        "ward": p.ward,
        "bed": p.bed,
        "admission_date": p.admission_date,
        "primary_diagnosis": p.primary_diagnosis,
        "risk_level": risk.level,
        "pending_exams_count": len(pending),
        "overdue_exams_count": len(overdue),
        "active_alerts_count": sum(1 for a in (p.alerts or []) if a.acknowledged_at is None),
    }


def detail(p: m.Patient) -> dict[str, Any]:
    base = summarize(p)
    now = datetime.now()
    exams = []
    for e in sorted(p.exams, key=lambda x: x.requested_at, reverse=True):
        d = {c.name: getattr(e, c.name) for c in e.__table__.columns}
        if d["status"] in ("pendente", "coletado") and is_overdue(
            {"status": d["status"], "due_at": d["due_at"]}, now
        ):
            d["status"] = "atrasado"
        exams.append(d)
    base.update(
        {
            "allergies": p.allergies,
            "comorbidities": p.comorbidities,
            "weight_kg": p.weight_kg,
            "height_cm": p.height_cm,
            "blood_type": p.blood_type,
            "vitals": sorted(p.vitals, key=lambda v: v.measured_at),
            "exams": exams,
            "medications": p.medications,
            "notes": sorted(p.notes, key=lambda n: n.created_at, reverse=True),
            "alerts": [alert_dict(a, p.name) for a in p.alerts],
        }
    )
    return base


def alert_dict(a: m.Alert, patient_name: str = "") -> dict[str, Any]:
    return {
        "id": a.id,
        "patient_id": a.patient_id,
        "patient_name": patient_name,
        "severity": a.severity,
        "title": a.title,
        "message": a.message,
        "source": a.source,
        "run_id": a.run_id,
        "created_at": a.created_at,
        "acknowledged_at": a.acknowledged_at,
        "acknowledged_by": a.acknowledged_by,
    }


# ---------------------------------------------------------------------------
# Contexto para a LLM — SEM PII
# ---------------------------------------------------------------------------
def build_context(
    p: m.Patient, professional_names: list[str] | None = None, now: datetime | None = None
) -> tuple[str, RiskAssessment, dict[str, int]]:
    """Monta o texto que a LLM recebe. Regras:
    - Identificação apenas por idade/sexo/setor (nunca nome, MRN, CPF, telefone, endereço).
    - Evoluções passam pelo Anonymizer (que também conhece o nome do paciente e dos profissionais).
    - Inclui risco determinístico (qSOFA/NEWS2/valores críticos/exames atrasados).
    """
    now = now or datetime.now()
    known = [p.name]
    if p.mother_name:
        known.append(p.mother_name)
    anon = Anonymizer(
        known_names=known + list(professional_names or []),
        professional_names=list(professional_names or []),
    )
    risk = risk_for(p, now)
    lines: list[str] = []
    lines.append(
        f"Paciente: sexo {p.sex}, {p.age} anos, setor {p.ward}, internado há {max(0, (now - p.admission_date).days)} dia(s)."
    )
    lines.append(f"Diagnóstico principal: {p.primary_diagnosis}.")
    if p.comorbidities:
        lines.append("Comorbidades: " + "; ".join(p.comorbidities) + ".")
    lines.append(
        "Alergias: " + ("; ".join(p.allergies) if p.allergies else "nenhuma registrada") + "."
    )
    lines.append(f"Peso {p.weight_kg} kg, altura {p.height_cm} cm.")
    lv = latest_vital(p)
    if lv:
        gcs = f", GCS {lv['gcs']}" if lv.get("gcs") is not None else ""
        lines.append(
            f"Sinais vitais ({_d(lv['measured_at'])}): FC {lv['hr']} bpm, PA {lv['sbp']}/{lv['dbp']} mmHg, FR {lv['rr']} irpm, T {lv['temp_c']} °C, SpO2 {lv['spo2']}%{gcs}."
        )
    done = [e for e in p.exams if e.result_value]
    if done:
        lines.append(
            "Exames recentes: "
            + "; ".join(
                f"{e.name} = {e.result_value}{(' ' + e.unit) if e.unit else ''}{' (CRÍTICO)' if e.is_critical else ''}"
                for e in sorted(done, key=lambda x: x.result_at or x.requested_at, reverse=True)[
                    :12
                ]
            )
            + "."
        )
    pend = [e for e in p.exams if e.status in ("pendente", "coletado", "atrasado")]
    if pend:
        lines.append(
            "Exames pendentes: "
            + "; ".join(
                f"{e.name} ({'ATRASADO' if is_overdue({'status': e.status, 'due_at': e.due_at}, now) else e.status})"
                for e in pend
            )
            + "."
        )
    meds = [md for md in p.medications if md.status == "ativo"]
    if meds:
        lines.append(
            "Medicações ativas: "
            + "; ".join(f"{md.name} {md.dose} {md.route} {md.frequency}" for md in meds)
            + "."
        )
    susp = [md for md in p.medications if md.status != "ativo"]
    if susp:
        lines.append("Suspensas: " + "; ".join(md.name for md in susp) + ".")
    pii_total: dict[str, int] = {}
    notes = sorted(p.notes, key=lambda n: n.created_at, reverse=True)[:3]
    if notes:
        lines.append("Últimas evoluções (anonimizadas):")
        for n in notes:
            r = anon.anonymize(n.text)
            for k, v in r.by_type.items():
                pii_total[k] = pii_total.get(k, 0) + v
            author_r = anon.anonymize(n.author)
            for k, v in author_r.by_type.items():
                pii_total[k] = pii_total.get(k, 0) + v
            lines.append(
                f"- [{_d(n.created_at)} · {n.type} · {author_r.text if author_r.count else '[PROFISSIONAL]'}] {r.text}"
            )
    lines.append(
        f"Avaliação de risco (regras): nível {risk.level.upper()} (score {risk.score}; qSOFA {risk.qsofa}; NEWS2 {risk.news2})."
    )
    if risk.factors:
        lines.append("Fatores: " + " | ".join(risk.factors))
    if risk.protocol_hints:
        lines.append("Protocolos possivelmente aplicáveis: " + ", ".join(risk.protocol_hints))
    text = "\n".join(lines)
    # cinto e suspensório: passa o texto final inteiro pelo anonimizador de novo
    final = anon.anonymize(text)
    for k, v in final.by_type.items():
        pii_total[k] = pii_total.get(k, 0) + v
    return final.text, risk, pii_total


async def professional_names(session: AsyncSession) -> list[str]:
    rows = (await session.execute(select(m.User.name))).scalars().all()
    return list(rows)
