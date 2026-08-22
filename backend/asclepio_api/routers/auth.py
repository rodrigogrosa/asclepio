from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..core import audit
from ..core.config import get_settings
from ..core.deps import CurrentUser, DbSession, client_ip
from ..core.policies import permissions_for
from ..core.security import create_access_token, verify_password
from ..db import models as m
from ..main_limiter import limiter
from ..schemas import LoginIn, TokenOut, UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: m.User) -> UserOut:
    initials = "".join(
        p[0] for p in u.name.replace("Dra.", "").replace("Dr.", "").replace("Enf.", "").split()[:2]
    ).upper()
    return UserOut(
        id=u.id,
        name=u.name,
        email=u.email,
        role=u.role,
        crm=u.crm,
        specialty=u.specialty,
        avatar_initials=initials,
        permissions=permissions_for(u.role),
    )


@router.post("/login", response_model=TokenOut)
@limiter.limit(lambda: f"{get_settings().login_rate_limit_per_minute}/minute")
async def login(
    request: Request, response: Response, body: LoginIn, session: DbSession
) -> TokenOut:
    s = get_settings()
    ip = client_ip(request)
    user = (
        await session.execute(select(m.User).where(m.User.email == body.email.lower().strip()))
    ).scalar_one_or_none()
    now = datetime.now()
    if user and user.locked_until and user.locked_until > now:
        await audit.record(
            session,
            action="auth.login_failed",
            user=user,
            ip=ip,
            details={"reason": "conta bloqueada temporariamente"},
        )
        raise HTTPException(
            status.HTTP_423_LOCKED,
            f"Conta bloqueada por tentativas inválidas. Tente novamente após {user.locked_until.strftime('%H:%M')}.",
        )
    if not user or not user.is_active or not verify_password(body.password, user.hashed_password):
        if user:
            user.failed_attempts = (user.failed_attempts or 0) + 1
            if user.failed_attempts >= s.max_failed_logins:
                user.locked_until = now + timedelta(minutes=s.lockout_minutes)
                user.failed_attempts = 0
            await session.commit()
        await audit.record(
            session,
            action="auth.login_failed",
            user=user,
            ip=ip,
            details={"email": body.email[:80], "reason": "credenciais inválidas"},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-mail ou senha inválidos")
    user.failed_attempts = 0
    user.locked_until = None
    user.last_login_at = now
    await session.commit()
    token, expires = create_access_token(subject=str(user.id), role=user.role)
    await audit.record(session, action="auth.login", user=user, ip=ip, details={"role": user.role})
    return TokenOut(access_token=token, expires_in=expires, user=user_out(user))


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.post("/logout")
async def logout(request: Request, user: CurrentUser, session: DbSession) -> dict[str, bool]:
    await audit.record(session, action="auth.logout", user=user, ip=client_ip(request))
    return {"ok": True}
