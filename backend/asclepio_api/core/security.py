"""Primitivas de segurança: hashing de senha (bcrypt), JWT e verificação de token."""

from __future__ import annotations

import base64
import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import bcrypt
import pyotp
import segno
from cryptography.fernet import Fernet, InvalidToken
from jose import JWTError, jwt

from .config import get_settings


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        return False


def create_access_token(
    *,
    subject: str,
    role: str,
    session_id: int | None = None,
    extra: dict[str, Any] | None = None,
    expires_minutes: int | None = None,
) -> tuple[str, int]:
    s = get_settings()
    minutes = expires_minutes or s.access_token_expire_minutes
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "iss": "asclepio-api",
        "sid": session_id,
        **(extra or {}),
    }
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm), minutes * 60


def decode_token(token: str) -> dict[str, Any] | None:
    s = get_settings()
    try:
        return jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm], issuer="asclepio-api")
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Tokens opacos (refresh) — só o hash vai para o banco
# ---------------------------------------------------------------------------
def new_opaque_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_temp_password(length: int = 14) -> str:
    """Senha temporária forte que satisfaz a política (maiúscula, minúscula, dígito, símbolo)."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"
    while True:
        core = "".join(secrets.choice(alphabet) for _ in range(length - 2))
        pwd = core + secrets.choice("!@#$%&*") + secrets.choice("23456789")
        if (
            any(c.isupper() for c in pwd)
            and any(c.islower() for c in pwd)
            and any(c.isdigit() for c in pwd)
        ):
            return pwd


# ---------------------------------------------------------------------------
# Token de desafio MFA (curto, propósito único)
# ---------------------------------------------------------------------------
def create_mfa_token(subject: str) -> tuple[str, int]:
    s = get_settings()
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "purpose": "mfa",
        "jti": uuid.uuid4().hex,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=s.mfa_token_expire_minutes)).timestamp()),
        "iss": "asclepio-api",
    }
    return jwt.encode(
        payload, s.secret_key, algorithm=s.jwt_algorithm
    ), s.mfa_token_expire_minutes * 60


def decode_mfa_token(token: str) -> dict[str, Any] | None:
    payload = decode_token(token)
    if not payload or payload.get("purpose") != "mfa":
        return None
    return payload


# ---------------------------------------------------------------------------
# TOTP (app autenticador) — segredo cifrado em repouso com Fernet derivado do SECRET_KEY
# ---------------------------------------------------------------------------
def _fernet() -> Fernet:
    key = hashlib.sha256(("asclepio-mfa:" + get_settings().secret_key).encode()).digest()
    return Fernet(base64.urlsafe_b64encode(key))


def encrypt_secret(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_secret(cipher: str) -> str | None:
    try:
        return _fernet().decrypt(cipher.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def new_totp_secret() -> str:
    return pyotp.random_base32()


def totp_uri(secret: str, email: str, issuer: str | None = None) -> str:
    """URI otpauth:// curta e compatível (issuer ASCII sem espaços, '@' sem percent-encoding,
    parâmetros explícitos) — QR menos denso e aceito por Google Authenticator/Authy/1Password/Microsoft."""
    import unicodedata
    from urllib.parse import quote

    if issuer is None:
        issuer = get_settings().app_name
    issuer_ascii = unicodedata.normalize("NFKD", issuer).encode("ascii", "ignore").decode()
    issuer_ascii = "".join(ch for ch in issuer_ascii if ch.isalnum() or ch in "-_.") or "Asclepio"
    label = quote(f"{issuer_ascii}:{email}", safe="@:")
    return f"otpauth://totp/{label}?secret={secret}&issuer={issuer_ascii}&algorithm=SHA1&digits=6&period=30"


def totp_qr_svg(uri: str) -> str:
    """SVG inline do QR (nível de correção M, borda quieta de 4 módulos, módulos grandes) — fácil de escanear da tela."""
    return segno.make(uri, error="m", boost_error=False).svg_inline(
        scale=8, dark="#0B0B10", light="#FFFFFF", border=4
    )


def verify_totp(secret: str, code: str) -> bool:
    code = (code or "").strip().replace(" ", "")
    if not code.isdigit() or len(code) != 6:
        return False
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def generate_recovery_codes(n: int = 10) -> list[str]:
    return [f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}" for _ in range(n)]


def hash_recovery_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().replace(" ", "").encode()).hexdigest()
