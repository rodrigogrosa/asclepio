"""Seed idempotente: usuários de demonstração + pacientes sintéticos (asclepio_core.synthetic)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from asclepio_core.clinical_rules import evaluate_labs
from asclepio_core.synthetic import generate_patients
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.config import get_settings
from ..core.logging import get_logger
from ..core.policies import DEFAULT_PASSWORD_POLICY
from ..core.security import hash_password
from . import models as m

log = get_logger("seed")

DEMO_PASSWORD = "Asclepio@2026"

DEMO_USERS = [
    {
        "name": "Administrador do Sistema",
        "email": "admin@asclepio.fiap",
        "role": "admin",
        "crm": None,
        "specialty": "TI / Governança",
    },
    {
        "name": "Dra. Ana Beatriz Souza",
        "email": "dra.ana@asclepio.fiap",
        "role": "medico",
        "crm": "CRM 123456-SP",
        "specialty": "Clínica Médica",
    },
    {
        "name": "Dr. Marcos Vinícius Lima",
        "email": "dr.marcos@asclepio.fiap",
        "role": "medico",
        "crm": "CRM 654321-SP",
        "specialty": "Medicina de Emergência",
    },
    {
        "name": "Enf. Carla Mendes",
        "email": "enf.carla@asclepio.fiap",
        "role": "enfermagem",
        "crm": "COREN 98765-SP",
        "specialty": "Enfermagem Clínica",
    },
    {
        "name": "Auditoria Clínica",
        "email": "auditor@asclepio.fiap",
        "role": "auditor",
        "crm": None,
        "specialty": "Qualidade e Segurança do Paciente",
    },
]


def _dt(s: str | None) -> datetime | None:
    return datetime.fromisoformat(s) if s else None


async def seed_users(session: AsyncSession) -> int:
    assert not DEFAULT_PASSWORD_POLICY.validate(DEMO_PASSWORD), "senha demo viola a política"
    count = 0
    for u in DEMO_USERS:
        exists = (
            await session.execute(select(m.User).where(m.User.email == u["email"]))
        ).scalar_one_or_none()
        if exists:
            continue
        session.add(m.User(hashed_password=hash_password(DEMO_PASSWORD), **u))
        count += 1
    await session.commit()
    return count


def _load_or_generate_patients() -> list[dict]:
    s = get_settings()
    p = Path(s.synthetic_patients_file)
    now = datetime.now().replace(microsecond=0)
    data = generate_patients(now=now)
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(
            json.dumps(
                {
                    "generated_at": now.isoformat(),
                    "disclaimer": "Dados 100% sintéticos/fictícios (Faker) — Tech Challenge FIAP.",
                    "patients": data,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    except OSError:
        pass
    return data


async def seed_patients(session: AsyncSession) -> int:
    total = (await session.execute(select(func.count(m.Patient.id)))).scalar_one()
    if total:
        return 0
    patients = _load_or_generate_patients()
    for p in patients:
        crit_names = {c.exam for c in evaluate_labs(p["exams"])}
        pat = m.Patient(
            mrn=p["mrn"],
            name=p["name"],
            sex=p["sex"],
            birth_date=p["birth_date"],
            cpf=p.get("cpf"),
            phone=p.get("phone"),
            address=p.get("address"),
            mother_name=p.get("mother_name"),
            ward=p["ward"],
            bed=p["bed"],
            admission_date=_dt(p["admission_date"]),
            primary_diagnosis=p["primary_diagnosis"],
            comorbidities=p["comorbidities"],
            allergies=p["allergies"],
            weight_kg=p["weight_kg"],
            height_cm=p["height_cm"],
            blood_type=p["blood_type"],
            scenario=p.get("scenario"),
        )
        for v in p["vitals"]:
            pat.vitals.append(
                m.Vital(
                    measured_at=_dt(v["measured_at"]),
                    hr=v["hr"],
                    sbp=v["sbp"],
                    dbp=v["dbp"],
                    rr=v["rr"],
                    temp_c=v["temp_c"],
                    spo2=v["spo2"],
                    gcs=v.get("gcs"),
                )
            )
        for e in p["exams"]:
            pat.exams.append(
                m.Exam(
                    name=e["name"],
                    category=e["category"],
                    status=e["status"],
                    requested_at=_dt(e["requested_at"]),
                    due_at=_dt(e.get("due_at")),
                    result_at=_dt(e.get("result_at")),
                    result_value=e.get("result_value"),
                    unit=e.get("unit"),
                    reference_range=e.get("reference_range"),
                    is_critical=e["name"] in crit_names,
                    note=e.get("note"),
                )
            )
        for md in p["medications"]:
            pat.medications.append(
                m.Medication(
                    name=md["name"],
                    dose=md["dose"],
                    route=md["route"],
                    frequency=md["frequency"],
                    started_at=_dt(md["started_at"]),
                    status=md["status"],
                )
            )
        for n in p["notes"]:
            pat.notes.append(
                m.ClinicalNote(
                    created_at=_dt(n["created_at"]),
                    author=n["author"],
                    type=n["type"],
                    text=n["text"],
                )
            )
        session.add(pat)
    await session.commit()
    return len(patients)


async def run_seed(session: AsyncSession) -> dict[str, int]:
    users = await seed_users(session)
    patients = await seed_patients(session)
    if users or patients:
        log.info("seed concluído", users=users, patients=patients)
    return {"users": users, "patients": patients}
