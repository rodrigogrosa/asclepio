from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from ..core import audit
from ..core.config import get_settings
from ..core.deps import CurrentUser, DbSession, client_ip
from ..core.policies import DEFAULT_PASSWORD_POLICY, MFA_REQUIRED_ROLES
from ..core.security import (
    create_access_token,
    create_mfa_token,
    decode_mfa_token,
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    hash_password,
    hash_recovery_code,
    new_totp_secret,
    totp_qr_svg,
    totp_uri,
    verify_password,
    verify_totp,
)
from ..db import models as m
from ..db.models import now_local
from ..main_limiter import limiter
from ..schemas import (
    ChangePasswordIn,
    LoginIn,
    LogoutIn,
    MfaDisableIn,
    MfaEnableIn,
    MfaSetupOut,
    MfaVerifyIn,
    RefreshIn,
    SessionOut,
    TokenOut,
    UserOut,
)
from ..services import auth as svc

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: m.User) -> UserOut:
    return UserOut(**svc.user_out(u))


async def _get_user(session: DbSession, user_id: int) -> m.User | None:
    return (await session.execute(select(m.User).where(m.User.id == user_id))).scalar_one_or_none()


def _mfa_code_ok(user: m.User, code: str) -> tuple[bool, str | None]:
    """Aceita código TOTP de 6 dígitos ou código de recuperação (uso único). Retorna (ok, método)."""
    code = (code or "").strip()
    secret = decrypt_secret(user.mfa_secret or "") if user.mfa_secret else None
    if secret and verify_totp(secret, code):
        return True, "totp"
    h = hash_recovery_code(code)
    if h in (user.mfa_recovery_codes or []):
        user.mfa_recovery_codes = [c for c in user.mfa_recovery_codes if c != h]
        return True, "recovery_code"
    return False, None


# ---------------------------------------------------------------------------
# Login (etapa 1) → TokenOut ou desafio MFA
# ---------------------------------------------------------------------------
@router.post("/login", response_model=None)
@limiter.limit(lambda: f"{get_settings().login_rate_limit_per_minute}/minute")
async def login(
    request: Request, response: Response, body: LoginIn, session: DbSession
) -> dict[str, Any]:
    s = get_settings()
    ip = client_ip(request)
    user = (
        await session.execute(select(m.User).where(m.User.email == body.email.lower().strip()))
    ).scalar_one_or_none()
    now = now_local()
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
    if user.mfa_enabled:
        token, expires = create_mfa_token(str(user.id))
        await audit.record(session, action="auth.login_mfa_challenge", user=user, ip=ip, details={})
        return {
            "mfa_required": True,
            "mfa_token": token,
            "expires_in": expires,
            "methods": ["totp", "recovery_code"],
        }
    return await svc.issue_tokens(session, user, request, ip)


# ---------------------------------------------------------------------------
# Login (etapa 2) — código do app autenticador ou código de recuperação
# ---------------------------------------------------------------------------
@router.post("/mfa/verify", response_model=TokenOut)
@limiter.limit(lambda: f"{get_settings().login_rate_limit_per_minute}/minute")
async def mfa_verify(
    request: Request, response: Response, body: MfaVerifyIn, session: DbSession
) -> dict[str, Any]:
    s = get_settings()
    ip = client_ip(request)
    payload = decode_mfa_token(body.mfa_token)
    if not payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Desafio MFA inválido ou expirado; faça login novamente"
        )
    user = await _get_user(session, int(payload["sub"]))
    if not user or not user.is_active or not user.mfa_enabled:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Desafio MFA inválido")
    if (user.failed_mfa_attempts or 0) >= s.max_failed_mfa:
        user.locked_until = now_local() + timedelta(minutes=s.lockout_minutes)
        user.failed_mfa_attempts = 0
        await session.commit()
        await audit.record(
            session,
            action="auth.mfa_failed",
            user=user,
            ip=ip,
            details={"reason": "limite de tentativas; conta bloqueada temporariamente"},
        )
        raise HTTPException(
            status.HTTP_423_LOCKED, "Muitas tentativas de MFA; conta bloqueada temporariamente"
        )
    ok, method = _mfa_code_ok(user, body.code)
    if not ok:
        user.failed_mfa_attempts = (user.failed_mfa_attempts or 0) + 1
        await session.commit()
        await audit.record(
            session,
            action="auth.mfa_failed",
            user=user,
            ip=ip,
            details={"attempts": user.failed_mfa_attempts},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Código inválido")
    user.failed_mfa_attempts = 0
    return await svc.issue_tokens(
        session,
        user,
        request,
        ip,
        action="auth.mfa_verify",
        details={"method": method, "recovery_codes_left": len(user.mfa_recovery_codes or [])},
    )


# ---------------------------------------------------------------------------
# Refresh com rotação e detecção de reuso
# ---------------------------------------------------------------------------
@router.post("/refresh", response_model=TokenOut)
async def refresh(request: Request, body: RefreshIn, session: DbSession) -> dict[str, Any]:
    ip = client_ip(request)
    sess = await svc.find_session_by_refresh(session, body.refresh_token)
    if sess is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Refresh token inválido")
    user = await _get_user(session, sess.user_id)
    if sess.revoked_at is not None:
        # Reuso de um refresh já rotacionado/revogado = possível roubo → derruba todas as sessões do usuário
        n = await svc.revoke_all_sessions(session, sess.user_id, "refresh_reuse_detected")
        await session.commit()
        await audit.record(
            session,
            action="auth.refresh_reuse_detected",
            user=user,
            ip=ip,
            resource_type="session",
            resource_id=sess.id,
            details={"revoked": n},
        )
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Refresh token reutilizado; todas as sessões foram encerradas por segurança",
        )
    if sess.expires_at <= now_local() or not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada")
    new_sess, raw = await svc.create_session(session, user, request, ip)
    await svc.revoke_session(session, sess, "rotated", replaced_by=new_sess.id)
    new_sess.last_used_at = now_local()
    await session.commit()
    access, expires = create_access_token(
        subject=str(user.id), role=user.role, session_id=new_sess.id
    )
    await audit.record(
        session,
        action="auth.refresh",
        user=user,
        ip=ip,
        resource_type="session",
        resource_id=new_sess.id,
        details={"previous": sess.id},
    )
    return {
        "access_token": access,
        "refresh_token": raw,
        "token_type": "bearer",
        "expires_in": expires,
        "refresh_expires_in": get_settings().refresh_token_expire_hours * 3600,
        "user": svc.user_out(user),
        "must_change_password": bool(user.must_change_password),
    }


@router.get("/me", response_model=UserOut)
async def me(user: CurrentUser) -> UserOut:
    return user_out(user)


@router.post("/logout")
async def logout(
    request: Request, user: CurrentUser, session: DbSession, body: LogoutIn | None = None
) -> dict[str, Any]:
    ip = client_ip(request)
    sess = None
    if body and body.refresh_token:
        sess = await svc.find_session_by_refresh(session, body.refresh_token)
        if sess and sess.user_id != user.id:
            sess = None
    if sess is None:
        sess = getattr(request.state, "session", None)
    if sess is not None:
        await svc.revoke_session(session, sess, "logout")
        await session.commit()
    await audit.record(
        session,
        action="auth.logout",
        user=user,
        ip=ip,
        resource_type="session",
        resource_id=sess.id if sess else None,
    )
    return {"ok": True}


@router.post("/logout-all")
async def logout_all(request: Request, user: CurrentUser, session: DbSession) -> dict[str, Any]:
    n = await svc.revoke_all_sessions(session, user.id, "logout_all")
    await session.commit()
    await audit.record(
        session,
        action="auth.session_revoke",
        user=user,
        ip=client_ip(request),
        details={"revoked": n, "scope": "all"},
    )
    return {"ok": True, "revoked": n}


@router.post("/change-password")
async def change_password(
    request: Request, body: ChangePasswordIn, user: CurrentUser, session: DbSession
) -> dict[str, Any]:
    if not verify_password(body.current_password, user.hashed_password):
        await audit.record(
            session,
            action="auth.password_change_failed",
            user=user,
            ip=client_ip(request),
            details={"reason": "senha atual incorreta"},
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha atual incorreta")
    problems = DEFAULT_PASSWORD_POLICY.validate(body.new_password)
    if problems:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Nova senha não atende à política: " + ", ".join(problems),
        )
    if body.new_password == body.current_password:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "A nova senha deve ser diferente da atual"
        )
    user.hashed_password = hash_password(body.new_password)
    user.password_changed_at = now_local()
    user.must_change_password = False
    current = getattr(request.state, "session", None)
    n = await svc.revoke_all_sessions(
        session, user.id, "password_changed", keep_id=current.id if current else None
    )
    await session.commit()
    await audit.record(
        session,
        action="auth.password_change",
        user=user,
        ip=client_ip(request),
        details={"other_sessions_revoked": n},
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# MFA (TOTP — Google Authenticator, Authy, 1Password, etc.)
# ---------------------------------------------------------------------------
@router.get("/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(user: CurrentUser, session: DbSession) -> dict[str, str]:
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA já está ativo")
    secret = new_totp_secret()
    user.mfa_pending_secret = encrypt_secret(secret)
    await session.commit()
    uri = totp_uri(secret, user.email)
    return {"secret": secret, "otpauth_uri": uri, "qr_svg": totp_qr_svg(uri)}


@router.post("/mfa/enable")
async def mfa_enable(
    request: Request, body: MfaEnableIn, user: CurrentUser, session: DbSession
) -> dict[str, Any]:
    if user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA já está ativo")
    secret = decrypt_secret(user.mfa_pending_secret or "") if user.mfa_pending_secret else None
    if not secret:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Inicie a configuração em GET /auth/mfa/setup"
        )
    if not verify_totp(secret, body.code):
        await audit.record(
            session,
            action="auth.mfa_failed",
            user=user,
            ip=client_ip(request),
            details={"stage": "enable"},
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Código inválido — confira o relógio do celular e tente de novo",
        )
    codes = generate_recovery_codes()
    user.mfa_secret = user.mfa_pending_secret
    user.mfa_pending_secret = None
    user.mfa_enabled = True
    user.mfa_recovery_codes = [hash_recovery_code(c) for c in codes]
    user.failed_mfa_attempts = 0
    await session.commit()
    await audit.record(
        session,
        action="auth.mfa_enable",
        user=user,
        ip=client_ip(request),
        details={"recovery_codes": len(codes)},
    )
    return {"ok": True, "recovery_codes": codes}


@router.post("/mfa/disable")
async def mfa_disable(
    request: Request, body: MfaDisableIn, user: CurrentUser, session: DbSession
) -> dict[str, Any]:
    if not user.mfa_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA não está ativo")
    if get_settings().mfa_required_for_admin and user.role in MFA_REQUIRED_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "MFA é obrigatório para administradores e não pode ser desativado",
        )
    if not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Senha incorreta")
    ok, _ = _mfa_code_ok(user, body.code)
    if not ok:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Código inválido")
    user.mfa_enabled = False
    user.mfa_secret = None
    user.mfa_recovery_codes = []
    current = getattr(request.state, "session", None)
    await svc.revoke_all_sessions(
        session, user.id, "mfa_disabled", keep_id=current.id if current else None
    )
    await session.commit()
    await audit.record(session, action="auth.mfa_disable", user=user, ip=client_ip(request))
    return {"ok": True}


# ---------------------------------------------------------------------------
# Sessões
# ---------------------------------------------------------------------------
@router.get("/sessions", response_model=list[SessionOut])
async def sessions(request: Request, user: CurrentUser, session: DbSession) -> list[dict[str, Any]]:
    current = getattr(request.state, "session", None)
    rows = (
        (
            await session.execute(
                select(m.Session)
                .where(
                    m.Session.user_id == user.id,
                    m.Session.revoked_at.is_(None),
                    m.Session.expires_at > now_local(),
                )
                .order_by(m.Session.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": r.id,
            "created_at": r.created_at,
            "last_used_at": r.last_used_at,
            "expires_at": r.expires_at,
            "ip": r.ip,
            "user_agent": r.user_agent,
            "current": bool(current and current.id == r.id),
        }
        for r in rows
    ]


@router.delete("/sessions/{session_id}")
async def revoke(
    session_id: int, request: Request, user: CurrentUser, session: DbSession
) -> dict[str, bool]:
    sess = (
        await session.execute(
            select(m.Session).where(m.Session.id == session_id, m.Session.user_id == user.id)
        )
    ).scalar_one_or_none()
    if not sess:
        raise HTTPException(404, "Sessão não encontrada")
    await svc.revoke_session(session, sess, "revoked_by_user")
    await session.commit()
    await audit.record(
        session,
        action="auth.session_revoke",
        user=user,
        ip=client_ip(request),
        resource_type="session",
        resource_id=session_id,
    )
    return {"ok": True}


_ = datetime  # mantém import para tipos em docs
