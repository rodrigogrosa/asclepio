"""Rate limiter compartilhado (slowapi) — separado para evitar import circular."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from .core.config import get_settings

limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[f"{get_settings().rate_limit_per_minute}/minute"],
    headers_enabled=True,
)
