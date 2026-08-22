"""Configuração pública (sem autenticação) usada pelo frontend para branding e modo de operação."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from ..core.config import get_settings
from ..core.policies import MFA_REQUIRED_ROLES

router = APIRouter(prefix="/public", tags=["público"])


@router.get("/config")
async def public_config() -> dict[str, Any]:
    s = get_settings()
    return {
        "app_name": s.app_name,
        "hospital_name": s.app_hospital_name,
        "hospital_short_name": s.app_hospital_short_name,
        "version": s.app_version,
        "demo_mode": bool(s.seed_demo_users),
        "mfa_required_roles": sorted(MFA_REQUIRED_ROLES) if s.mfa_required_for_admin else [],
        "support_email": s.app_support_email or None,
    }
