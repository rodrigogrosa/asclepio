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
from ..core.security import generate_temp_password, hash_password, verify_password
from . import models as m

log = get_logger("seed")

DEMO_PASSWORD = "Asclepio@2026"

DEMO_USERS = [
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


async def _ensure_real_user(
    session: AsyncSession, *, name: str, email: str, role: str, password: str | None, specialty: str
) -> int:
    """Cria um usuário REAL (ex.: admin) com senha forte. Sem senha configurada, gera uma, registra no
    log UMA vez e força a troca no primeiro acesso."""
    exists = (
        await session.execute(select(m.User).where(m.User.email == email))
    ).scalar_one_or_none()
    if exists:
        # Upgrade de bancos antigos: usuário real ainda com a senha de demonstração → vira conta real
        if exists.is_demo or verify_password(DEMO_PASSWORD, exists.hashed_password):
            pwd = password or generate_temp_password(16)
            exists.hashed_password = hash_password(pwd)
            exists.must_change_password = True
            exists.is_demo = False
            exists.role = role
            log.warning(
                "usuário real atualizado (tinha senha de demonstração) — troca obrigatória no 1º acesso",
                email=email,
                password=None if password else pwd,
            )
        return 0
    generated = False
    if not password:
        password = generate_temp_password(16)
        generated = True
    problems = DEFAULT_PASSWORD_POLICY.validate(password)
    if problems:
        raise RuntimeError(
            f"Senha configurada para {email} viola a política: {', '.join(problems)}"
        )
    session.add(
        m.User(
            name=name,
            email=email,
            role=role,
            specialty=specialty,
            crm=None,
            hashed_password=hash_password(password),
            must_change_password=True,
            is_demo=False,
        )
    )
    if generated:
        log.warning(
            "SENHA INICIAL GERADA (anote agora; troca obrigatória no primeiro acesso)",
            email=email,
            password=password,
        )
    return 1


async def seed_users(session: AsyncSession) -> int:
    s = get_settings()
    count = 0
    # Usuários reais (admin do sistema + Rodrigo Rosa)
    count += await _ensure_real_user(
        session,
        name="Administrador do Sistema",
        email=s.admin_email,
        role="admin",
        password=s.admin_password,
        specialty="TI / Governança",
    )
    count += await _ensure_real_user(
        session,
        name=s.rodrigo_name,
        email=s.rodrigo_email,
        role="admin",
        password=s.rodrigo_password,
        specialty="Engenharia de IA",
    )
    # Usuários de demonstração (ambiente acadêmico; SEED_DEMO_USERS=false em produção)
    if s.seed_demo_users:
        assert not DEFAULT_PASSWORD_POLICY.validate(DEMO_PASSWORD), "senha demo viola a política"
        for u in DEMO_USERS:
            exists = (
                await session.execute(select(m.User).where(m.User.email == u["email"]))
            ).scalar_one_or_none()
            if exists:
                continue
            session.add(m.User(hashed_password=hash_password(DEMO_PASSWORD), is_demo=True, **u))
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


SPECIALTIES = [
    ("Anestesiologia", "ANE"),
    ("Cardiologia", "CAR"),
    ("Cirurgia Geral", "CIR"),
    ("Clínica Médica", "CLM"),
    ("Dermatologia", "DER"),
    ("Endocrinologia e Metabologia", "END"),
    ("Gastroenterologia", "GAS"),
    ("Geriatria", "GER"),
    ("Ginecologia e Obstetrícia", "GOB"),
    ("Hematologia e Hemoterapia", "HEM"),
    ("Infectologia", "INF"),
    ("Medicina de Emergência", "EME"),
    ("Medicina de Família e Comunidade", "MFC"),
    ("Medicina Intensiva", "UTI"),
    ("Nefrologia", "NEF"),
    ("Neurologia", "NEU"),
    ("Neurocirurgia", "NCR"),
    ("Oftalmologia", "OFT"),
    ("Oncologia Clínica", "ONC"),
    ("Ortopedia e Traumatologia", "ORT"),
    ("Otorrinolaringologia", "OTO"),
    ("Pediatria", "PED"),
    ("Pneumologia", "PNE"),
    ("Psiquiatria", "PSQ"),
    ("Radiologia e Diagnóstico por Imagem", "RAD"),
    ("Reumatologia", "REU"),
    ("Urologia", "URO"),
    ("Enfermagem Clínica", "ENF"),
    ("Enfermagem em Terapia Intensiva", "ENT"),
    ("Farmácia Clínica", "FAR"),
    ("Qualidade e Segurança do Paciente", "QSP"),
    ("Engenharia de IA", "IA"),
    ("TI / Governança", "TI"),
]
SECTORS = [
    ("Pronto-Socorro", "pronto_socorro"),
    ("Clínica Médica", "internacao"),
    ("Cardiologia", "internacao"),
    ("Unidade Coronariana", "uti"),
    ("UTI Adulto", "uti"),
    ("Cirurgia Geral", "cirurgico"),
    ("Ortopedia", "internacao"),
    ("Geriatria", "internacao"),
    ("Pneumologia", "internacao"),
    ("Ambulatório", "ambulatorio"),
]


async def seed_catalogs(session: AsyncSession) -> int:
    n = 0
    existing = {r.name for r in (await session.execute(select(m.Specialty))).scalars().all()}
    for name, code in SPECIALTIES:
        if name not in existing:
            session.add(m.Specialty(name=name, code=code))
            n += 1
    existing_s = {r.name for r in (await session.execute(select(m.Sector))).scalars().all()}
    for name, kind in SECTORS:
        if name not in existing_s:
            session.add(m.Sector(name=name, kind=kind))
            n += 1
    await session.commit()
    # vincula specialty_id dos usuários pelo nome textual (idempotente)
    specs = {r.name: r.id for r in (await session.execute(select(m.Specialty))).scalars().all()}
    sectors = {r.name: r.id for r in (await session.execute(select(m.Sector))).scalars().all()}
    for u in (await session.execute(select(m.User))).scalars().all():
        if u.specialty and not u.specialty_id and u.specialty in specs:
            u.specialty_id = specs[u.specialty]
        if u.role == "medico" and not u.sector_id:
            u.sector_id = sectors.get(
                "Pronto-Socorro" if "Emergência" in (u.specialty or "") else "Clínica Médica"
            )
        if u.role == "enfermagem" and not u.sector_id:
            u.sector_id = sectors.get("Clínica Médica")
        # bancos antigos: marca usuários de demonstração
        if (
            not u.is_demo
            and any(u.email == d["email"] for d in DEMO_USERS)
            and verify_password(DEMO_PASSWORD, u.hashed_password)
        ):
            u.is_demo = True
    await session.commit()
    return n


async def run_seed(session: AsyncSession) -> dict[str, int]:
    users = await seed_users(session)
    await seed_catalogs(session)
    patients = await seed_patients(session)
    if users or patients:
        log.info("seed concluído", users=users, patients=patients)
    return {"users": users, "patients": patients}
