"""Dependências FastAPI: sessão de banco, usuário autenticado e verificação de permissões."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.base import get_session
from ..db.models import User
from .policies import has_permission
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
        and user.password_changed_at
        and int(user.password_changed_at.timestamp()) - 5 > int(iat)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessão expirada (senha alterada)")
    request.state.user = user
    return user


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
