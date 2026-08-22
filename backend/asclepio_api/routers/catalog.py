"""Catálogos administráveis: especialidades médicas e setores do hospital."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..db import models as m

router = APIRouter(prefix="/catalog", tags=["catálogos"])

SECTOR_KINDS = ("pronto_socorro", "internacao", "uti", "ambulatorio", "cirurgico", "outro")


class SpecialtyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=20)


class SpecialtyPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=20)
    active: bool | None = None


class SectorIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    kind: str = "internacao"


class SectorPatch(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    kind: str | None = None
    active: bool | None = None


async def _spec_counts(session: DbSession) -> dict[int, int]:
    rows = (
        await session.execute(
            select(m.User.specialty_id, func.count(m.User.id))
            .where(m.User.specialty_id.is_not(None))
            .group_by(m.User.specialty_id)
        )
    ).all()
    return {k: v for k, v in rows if k is not None}


async def _sector_counts(session: DbSession) -> dict[str, int]:
    rows = (
        await session.execute(
            select(m.Patient.ward, func.count(m.Patient.id)).group_by(m.Patient.ward)
        )
    ).all()
    return dict(rows)


@router.get("/specialties", dependencies=[require_permission("catalog:read")])
async def specialties(session: DbSession, include_inactive: bool = False) -> list[dict[str, Any]]:
    q = select(m.Specialty).order_by(m.Specialty.name)
    if not include_inactive:
        q = q.where(m.Specialty.active.is_(True))
    counts = await _spec_counts(session)
    return [
        {
            "id": s.id,
            "name": s.name,
            "code": s.code,
            "active": s.active,
            "professionals_count": counts.get(s.id, 0),
        }
        for s in (await session.execute(q)).scalars().all()
    ]


@router.post("/specialties", status_code=201, dependencies=[require_permission("catalog:manage")])
async def create_specialty(
    body: SpecialtyIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    if (
        await session.execute(
            select(m.Specialty).where(func.lower(m.Specialty.name) == body.name.strip().lower())
        )
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Especialidade já cadastrada")
    sp = m.Specialty(name=body.name.strip(), code=body.code)
    session.add(sp)
    await session.commit()
    await audit.record(
        session,
        action="catalog.specialty_create",
        user=user,
        resource_type="specialty",
        resource_id=sp.id,
        ip=client_ip(request),
        details={"name": sp.name},
    )
    return {
        "id": sp.id,
        "name": sp.name,
        "code": sp.code,
        "active": sp.active,
        "professionals_count": 0,
    }


@router.patch("/specialties/{sid}", dependencies=[require_permission("catalog:manage")])
async def update_specialty(
    sid: int, body: SpecialtyPatch, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    sp = (
        await session.execute(select(m.Specialty).where(m.Specialty.id == sid))
    ).scalar_one_or_none()
    if not sp:
        raise HTTPException(404, "Especialidade não encontrada")
    for f in ("name", "code", "active"):
        v = getattr(body, f)
        if v is not None:
            setattr(sp, f, v.strip() if isinstance(v, str) else v)
    await session.commit()
    await audit.record(
        session,
        action="catalog.specialty_update",
        user=user,
        resource_type="specialty",
        resource_id=sp.id,
        ip=client_ip(request),
        details=body.model_dump(exclude_none=True),
    )
    counts = await _spec_counts(session)
    return {
        "id": sp.id,
        "name": sp.name,
        "code": sp.code,
        "active": sp.active,
        "professionals_count": counts.get(sp.id, 0),
    }


@router.delete("/specialties/{sid}", dependencies=[require_permission("catalog:manage")])
async def delete_specialty(
    sid: int, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, bool]:
    sp = (
        await session.execute(select(m.Specialty).where(m.Specialty.id == sid))
    ).scalar_one_or_none()
    if not sp:
        raise HTTPException(404, "Especialidade não encontrada")
    if (await _spec_counts(session)).get(sid, 0):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Há profissionais vinculados; desative em vez de remover"
        )
    await session.delete(sp)
    await session.commit()
    await audit.record(
        session,
        action="catalog.specialty_delete",
        user=user,
        resource_type="specialty",
        resource_id=sid,
        ip=client_ip(request),
        details={"name": sp.name},
    )
    return {"ok": True}


@router.get("/sectors", dependencies=[require_permission("catalog:read")])
async def sectors(session: DbSession, include_inactive: bool = False) -> list[dict[str, Any]]:
    q = select(m.Sector).order_by(m.Sector.name)
    if not include_inactive:
        q = q.where(m.Sector.active.is_(True))
    counts = await _sector_counts(session)
    return [
        {
            "id": s.id,
            "name": s.name,
            "kind": s.kind,
            "active": s.active,
            "patients_count": counts.get(s.name, 0),
        }
        for s in (await session.execute(q)).scalars().all()
    ]


@router.post("/sectors", status_code=201, dependencies=[require_permission("catalog:manage")])
async def create_sector(
    body: SectorIn, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    if body.kind not in SECTOR_KINDS:
        raise HTTPException(422, f"kind inválido; use um de {SECTOR_KINDS}")
    if (
        await session.execute(
            select(m.Sector).where(func.lower(m.Sector.name) == body.name.strip().lower())
        )
    ).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Setor já cadastrado")
    sc = m.Sector(name=body.name.strip(), kind=body.kind)
    session.add(sc)
    await session.commit()
    await audit.record(
        session,
        action="catalog.sector_create",
        user=user,
        resource_type="sector",
        resource_id=sc.id,
        ip=client_ip(request),
        details={"name": sc.name},
    )
    return {"id": sc.id, "name": sc.name, "kind": sc.kind, "active": sc.active, "patients_count": 0}


@router.patch("/sectors/{sid}", dependencies=[require_permission("catalog:manage")])
async def update_sector(
    sid: int, body: SectorPatch, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, Any]:
    sc = (await session.execute(select(m.Sector).where(m.Sector.id == sid))).scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Setor não encontrado")
    if body.kind is not None and body.kind not in SECTOR_KINDS:
        raise HTTPException(422, "kind inválido")
    for f in ("name", "kind", "active"):
        v = getattr(body, f)
        if v is not None:
            setattr(sc, f, v.strip() if isinstance(v, str) else v)
    await session.commit()
    await audit.record(
        session,
        action="catalog.sector_update",
        user=user,
        resource_type="sector",
        resource_id=sc.id,
        ip=client_ip(request),
        details=body.model_dump(exclude_none=True),
    )
    counts = await _sector_counts(session)
    return {
        "id": sc.id,
        "name": sc.name,
        "kind": sc.kind,
        "active": sc.active,
        "patients_count": counts.get(sc.name, 0),
    }


@router.delete("/sectors/{sid}", dependencies=[require_permission("catalog:manage")])
async def delete_sector(
    sid: int, request: Request, session: DbSession, user: CurrentUser
) -> dict[str, bool]:
    sc = (await session.execute(select(m.Sector).where(m.Sector.id == sid))).scalar_one_or_none()
    if not sc:
        raise HTTPException(404, "Setor não encontrado")
    if (await _sector_counts(session)).get(sc.name, 0):
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Há pacientes neste setor; desative em vez de remover"
        )
    await session.delete(sc)
    await session.commit()
    await audit.record(
        session,
        action="catalog.sector_delete",
        user=user,
        resource_type="sector",
        resource_id=sid,
        ip=client_ip(request),
        details={"name": sc.name},
    )
    return {"ok": True}
