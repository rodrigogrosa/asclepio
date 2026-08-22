"""Gestão de usuários (admin): criar, atualizar, resetar senha e MFA. Tudo auditado."""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import select

from ..core import audit
from ..core.deps import CurrentUser, DbSession, client_ip, require_permission
from ..core.policies import DEFAULT_PASSWORD_POLICY, ROLES
from ..core.security import generate_temp_password, hash_password
from ..db import models as m
from ..db.models import now_local
from ..schemas import UserCreateIn, UserOut, UserUpdateIn
from ..services import auth as svc

router = APIRouter(
    prefix="/users", tags=["usuários"], dependencies=[require_permission("users:manage")]
)


async def _get(session: DbSession, user_id: int) -> m.User:
    u = (await session.execute(select(m.User).where(m.User.id == user_id))).scalar_one_or_none()
    if not u:
        raise HTTPException(404, "Usuário não encontrado")
    return u


CRM_RE = re.compile(r"^(CRM[- ]?)?\d{4,7}[-/ ]?[A-Z]{2}$", re.IGNORECASE)


def _normalize_crm(crm: str | None) -> str | None:
    if not crm:
        return None
    c = crm.strip().upper().replace("CRM-", "CRM ").replace("CRM", "").strip()
    c = re.sub(r"[/ ]", "-", c)
    if not CRM_RE.match("CRM " + c):
        raise HTTPException(422, "CRM inválido — use o formato CRM 123456-UF")
    return "CRM " + c


async def _validate_professional(
    session: DbSession, role: str, crm: str | None, specialty_id: int | None, sector_id: int | None
) -> tuple[str | None, str | None]:
    """Para médicos: CRM e especialidade obrigatórios. Resolve o nome da especialidade."""
    crm_n = _normalize_crm(crm)
    if role == "medico":
        if not crm_n:
            raise HTTPException(422, "CRM é obrigatório para médicos")
        if not specialty_id:
            raise HTTPException(422, "Especialidade é obrigatória para médicos")
    spec_name = None
    if specialty_id:
        sp = (
            await session.execute(select(m.Specialty).where(m.Specialty.id == specialty_id))
        ).scalar_one_or_none()
        if not sp or not sp.active:
            raise HTTPException(422, "Especialidade inexistente ou inativa")
        spec_name = sp.name
    if sector_id:
        sc = (
            await session.execute(select(m.Sector).where(m.Sector.id == sector_id))
        ).scalar_one_or_none()
        if not sc or not sc.active:
            raise HTTPException(422, "Setor inexistente ou inativo")
    return crm_n, spec_name


@router.get("", response_model=list[UserOut])
async def list_users(
    session: DbSession, role: str | None = None, active: bool | None = None, q: str | None = None
) -> list[dict[str, Any]]:
    qry = select(m.User).order_by(m.User.role, m.User.name)
    if role:
        qry = qry.where(m.User.role == role)
    if active is not None:
        qry = qry.where(m.User.is_active.is_(active))
    if q:
        like = f"%{q.lower()}%"
        qry = qry.where(
            (m.User.name.ilike(like))
            | (m.User.email.ilike(like))
            | (m.User.crm.ilike(like))
            | (m.User.specialty.ilike(like))
        )
    rows = (await session.execute(qry)).scalars().all()
    return [svc.user_out(u) for u in rows]


@router.get("/{user_id}", response_model=UserOut)
async def get_user(user_id: int, session: DbSession) -> dict[str, Any]:
    return svc.user_out(await _get(session, user_id))


@router.post("", status_code=201)
async def create_user(
    body: UserCreateIn, request: Request, session: DbSession, admin: CurrentUser
) -> dict[str, Any]:
    email = body.email.lower().strip()
    if body.role not in ROLES:
        raise HTTPException(422, "Papel inválido")
    if (await session.execute(select(m.User).where(m.User.email == email))).scalar_one_or_none():
        raise HTTPException(status.HTTP_409_CONFLICT, "Já existe usuário com este e-mail")
    crm_n, spec_name = await _validate_professional(
        session, body.role, body.crm, body.specialty_id, body.sector_id
    )
    temp = None
    password = body.password
    if password:
        problems = DEFAULT_PASSWORD_POLICY.validate(password)
        if problems:
            raise HTTPException(422, "Senha não atende à política: " + ", ".join(problems))
    else:
        password = temp = generate_temp_password()
    u = m.User(
        name=body.name.strip(),
        email=email,
        role=body.role,
        crm=crm_n,
        specialty=spec_name or body.specialty,
        specialty_id=body.specialty_id,
        sector_id=body.sector_id,
        hashed_password=hash_password(password),
        must_change_password=True,
        is_demo=False,
    )
    session.add(u)
    await session.commit()
    await audit.record(
        session,
        action="user.create",
        user=admin,
        resource_type="user",
        resource_id=u.id,
        ip=client_ip(request),
        details={"email": email, "role": body.role, "temporary_password": bool(temp)},
    )
    return {"user": svc.user_out(u), "temporary_password": temp}


@router.patch("/{user_id}", response_model=UserOut)
async def update_user(
    user_id: int, body: UserUpdateIn, request: Request, session: DbSession, admin: CurrentUser
) -> dict[str, Any]:
    u = await _get(session, user_id)
    changes: dict[str, Any] = {}
    if body.role is not None and body.role != u.role:
        if u.id == admin.id and body.role != "admin":
            raise HTTPException(400, "Você não pode remover o próprio papel de administrador")
        changes["role"] = (u.role, body.role)
        u.role = body.role
    if body.is_active is not None and body.is_active != u.is_active:
        if u.id == admin.id and not body.is_active:
            raise HTTPException(400, "Você não pode desativar a própria conta")
        changes["is_active"] = (u.is_active, body.is_active)
        u.is_active = body.is_active
        if not body.is_active:
            await svc.revoke_all_sessions(session, u.id, "deactivated")
    new_role = body.role or u.role
    if (
        body.crm is not None
        or body.specialty_id is not None
        or body.sector_id is not None
        or body.role is not None
    ):
        crm_n, spec_name = await _validate_professional(
            session,
            new_role,
            body.crm if body.crm is not None else u.crm,
            body.specialty_id if body.specialty_id is not None else u.specialty_id,
            body.sector_id if body.sector_id is not None else u.sector_id,
        )
        if body.crm is not None and crm_n != u.crm:
            changes["crm"] = (u.crm, crm_n)
            u.crm = crm_n
        if body.specialty_id is not None and body.specialty_id != u.specialty_id:
            changes["specialty_id"] = (u.specialty_id, body.specialty_id)
            u.specialty_id = body.specialty_id
            u.specialty = spec_name
        if body.sector_id is not None and body.sector_id != u.sector_id:
            changes["sector_id"] = (u.sector_id, body.sector_id)
            u.sector_id = body.sector_id
    for f in ("name", "specialty"):
        v = getattr(body, f)
        if v is not None and v != getattr(u, f):
            changes[f] = (getattr(u, f), v)
            setattr(u, f, v)
    await session.commit()
    await audit.record(
        session,
        action="user.update",
        user=admin,
        resource_type="user",
        resource_id=u.id,
        ip=client_ip(request),
        details={"changes": changes},
    )
    return svc.user_out(u)


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: int, request: Request, session: DbSession, admin: CurrentUser
) -> dict[str, str]:
    u = await _get(session, user_id)
    temp = generate_temp_password()
    u.hashed_password = hash_password(temp)
    u.password_changed_at = now_local()
    u.must_change_password = True
    u.failed_attempts = 0
    u.locked_until = None
    n = await svc.revoke_all_sessions(session, u.id, "password_reset_by_admin")
    await session.commit()
    await audit.record(
        session,
        action="user.reset_password",
        user=admin,
        resource_type="user",
        resource_id=u.id,
        ip=client_ip(request),
        details={"sessions_revoked": n},
    )
    return {"temporary_password": temp}


@router.post("/{user_id}/mfa/reset")
async def reset_mfa(
    user_id: int, request: Request, session: DbSession, admin: CurrentUser
) -> dict[str, bool]:
    u = await _get(session, user_id)
    u.mfa_enabled = False
    u.mfa_secret = None
    u.mfa_pending_secret = None
    u.mfa_recovery_codes = []
    u.failed_mfa_attempts = 0
    n = await svc.revoke_all_sessions(session, u.id, "mfa_reset_by_admin")
    await session.commit()
    await audit.record(
        session,
        action="user.mfa_reset",
        user=admin,
        resource_type="user",
        resource_id=u.id,
        ip=client_ip(request),
        details={"sessions_revoked": n},
    )
    return {"ok": True}
