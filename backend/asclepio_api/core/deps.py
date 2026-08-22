"""Dependências FastAPI: sessão de banco, usuário autenticado e verificação de permissões."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import get_session
from ..db.models import Session, User
from .config import get_settings
from .policies import MFA_REQUIRED_ROLES, has_permission
from .security import decode_token

bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_session)]


async def get_current_user(
    request: Request,
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    session: DbSession,
) -> User:
    if creds is None or not creds.credentials:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Não autenticado", headers={"WWW-Authenticate": "Bearer"}
        )
    payload = decode_token(creds.credentials)
    if not payload or "sub" not in payload:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Token inválido ou expirado",
            headers={"WWW-Authenticate": "Bearer"},
        )
    user = (
        await session.execute(select(User).where(User.id == int(payload["sub"])))
    ).scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuário inativo ou inexistente")
    # Política: token emitido antes da última troca de senha é inválido
    iat = payload.get("iat")
    if (
        iat
        and payload.get("sid") is None
        and user.password_changed_at
        and int(user.password_changed_at.timestamp()) - 5 > int(iat)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada (senha alterada)")
    # Política: o access token só vale enquanto a sessão (refresh) estiver ativa → logout/revogação imediatos
    sid = payload.get("sid")
    if sid is not None:
        sess = (
            await session.execute(select(Session).where(Session.id == int(sid)))
        ).scalar_one_or_none()
        if sess is None or sess.user_id != user.id or not sess.active:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Sessão encerrada ou expirada",
                headers={"WWW-Authenticate": "Bearer"},
            )
        request.state.session = sess
    # Gates de conta: troca de senha obrigatória e MFA obrigatório para admins (exceto rotas /auth/*)
    if not _is_auth_path(request.url.path):
        if user.must_change_password:
            raise HTTPException(
                status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "detail": "Troca de senha obrigatória no primeiro acesso",
                    "code": "password_change_required",
                },
            )
        if (
            get_settings().mfa_required_for_admin
            and user.role in MFA_REQUIRED_ROLES
            and not user.mfa_enabled
        ):
            raise HTTPException(
                status.HTTP_428_PRECONDITION_REQUIRED,
                detail={
                    "detail": "MFA obrigatório para administradores",
                    "code": "mfa_required_setup",
                },
            )
    request.state.user = user
    return user


def _is_auth_path(path: str) -> bool:
    return "/auth/" in path


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_permission(*permissions: str) -> Callable:  # type: ignore[type-arg]
    """Exige que o papel do usuário possua TODAS as permissões indicadas (ver core/policies.py)."""

    async def _check(user: CurrentUser) -> User:
        missing = [p for p in permissions if not has_permission(user.role, p)]
        if missing:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Permissão negada para o papel '{user.role}': {', '.join(missing)}",
            )
        return user

    return Depends(_check)


def client_ip(request: Request) -> str | None:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None
