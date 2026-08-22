"""Sessões, emissão de tokens e MFA — lógica reutilizada pelos routers de auth/usuários."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..core import audit
from ..core.config import get_settings
from ..core.policies import permissions_for
from ..core.security import create_access_token, hash_token, new_opaque_token
from ..db import models as m
from ..db.models import now_local


def user_out(u: m.User) -> dict[str, Any]:
    initials = "".join(
        p[0] for p in u.name.replace("Dra.", "").replace("Dr.", "").replace("Enf.", "").split()[:2]
    ).upper()
    return {
        "id": u.id,
        "name": u.name,
        "email": u.email,
        "role": u.role,
        "crm": u.crm,
        "specialty": u.specialty,
        "avatar_initials": initials,
        "permissions": permissions_for(u.role),
        "mfa_enabled": bool(u.mfa_enabled),
        "must_change_password": bool(u.must_change_password),
        "is_active": bool(u.is_active),
        "is_demo": bool(u.is_demo),
        "last_login_at": u.last_login_at,
        "created_at": u.created_at,
        "specialty_id": u.specialty_id,
        "sector_id": u.sector_id,
    }


def _ua(request: Request | None) -> str | None:
    if request is None:
        return None
    return (request.headers.get("user-agent") or "")[:200] or None


async def create_session(
    session: AsyncSession, user: m.User, request: Request | None, ip: str | None
) -> tuple[m.Session, str]:
    s = get_settings()
    raw = new_opaque_token()
    sess = m.Session(
        user_id=user.id,
        refresh_token_hash=hash_token(raw),
        expires_at=now_local() + timedelta(hours=s.refresh_token_expire_hours),
        ip=ip,
        user_agent=_ua(request),
    )
    session.add(sess)
    await session.flush()
    return sess, raw


async def issue_tokens(
    session: AsyncSession,
    user: m.User,
    request: Request | None,
    ip: str | None,
    *,
    action: str = "auth.login",
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Cria sessão + access token (com sid) e registra auditoria. Retorna o TokenOut como dict."""
    s = get_settings()
    sess, raw = await create_session(session, user, request, ip)
    user.last_login_at = now_local()
    user.failed_attempts = 0
    user.locked_until = None
    await session.commit()
    access, expires = create_access_token(subject=str(user.id), role=user.role, session_id=sess.id)
    await audit.record(
        session,
        action=action,
        user=user,
        resource_type="session",
        resource_id=sess.id,
        ip=ip,
        details={"role": user.role, "mfa": bool(user.mfa_enabled), **(details or {})},
    )
    return {
        "access_token": access,
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": expires,
        "refresh_expires_in": s.refresh_token_expire_hours * 3600,
        "user": user_out(user),
        "must_change_password": bool(user.must_change_password),
    }


async def revoke_session(
    session: AsyncSession, sess: m.Session, reason: str, replaced_by: int | None = None
) -> None:
    if sess.revoked_at is None:
        sess.revoked_at = now_local()
        sess.revoked_reason = reason
        sess.replaced_by_id = replaced_by


async def revoke_all_sessions(
    session: AsyncSession, user_id: int, reason: str, keep_id: int | None = None
) -> int:
    q = select(m.Session).where(m.Session.user_id == user_id, m.Session.revoked_at.is_(None))
    rows = (await session.execute(q)).scalars().all()
    n = 0
    for r in rows:
        if keep_id is not None and r.id == keep_id:
            continue
        await revoke_session(session, r, reason)
        n += 1
    await session.flush()
    return n


async def find_session_by_refresh(session: AsyncSession, raw: str) -> m.Session | None:
    return (
        await session.execute(
            select(m.Session).where(m.Session.refresh_token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()


async def touch_session(session: AsyncSession, sess_id: int) -> None:
    await session.execute(
        update(m.Session).where(m.Session.id == sess_id).values(last_used_at=now_local())
    )
