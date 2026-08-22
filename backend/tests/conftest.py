"""Fixtures: app em modo *fake* (sem Ollama/rede), banco SQLite temporário, clientes autenticados."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_TMP = Path(os.environ.get("PYTEST_TMP", "/tmp")) / "asclepio-tests"
_TMP.mkdir(parents=True, exist_ok=True)
for f in _TMP.glob("test.sqlite*"):
    f.unlink()

os.environ.update(
    {
        "APP_ENV": "test",
        "LLM_PROVIDER": "fake",
        "EMBEDDINGS_PROVIDER": "fake",
        "DATABASE_URL": f"sqlite+aiosqlite:///{_TMP / 'test.sqlite'}",
        "VECTORSTORE_DIR": str(_TMP / "vs"),
        "CHECKPOINTS_DIR": str(_TMP / "ckpt"),
        "SYNTHETIC_PATIENTS_FILE": str(_TMP / "patients.json"),
        "RATE_LIMIT_PER_MINUTE": "1000",
        "LOGIN_RATE_LIMIT_PER_MINUTE": "1000",
        "LOG_LEVEL": "WARNING",
        "SECRET_KEY": "test-secret-key-not-for-production-0123456789",
        "ASCLEPIO_ADMIN_PASSWORD": "Admin#Inicial2026",
        "ASCLEPIO_RODRIGO_PASSWORD": "Rodrigo#Inicial2026",
        "SEED_DEMO_USERS": "true",
    }
)

from asclepio_api.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

PASSWORD = "Asclepio@2026"


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


def _login(client: TestClient, email: str) -> dict[str, str]:
    r = client.post("/api/v1/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def medico(client):
    return _login(client, "dra.ana@asclepio.fiap")


@pytest.fixture
def enfermagem(client):
    return _login(client, "enf.carla@asclepio.fiap")


ADMIN_PASSWORD = "Admin#Novo2026!"


def admin_onboarding(
    client: TestClient, email: str, initial_password: str, new_password: str
) -> dict[str, str]:
    """Fluxo real do admin: login → troca de senha obrigatória → ativa MFA (TOTP) → login com código."""
    import pyotp

    r = client.post("/api/v1/auth/login", json={"email": email, "password": initial_password})
    assert r.status_code == 200, r.text
    tok = r.json()
    assert tok.get("must_change_password") is True
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    # qualquer rota fora de /auth → 428 enquanto não trocar a senha
    assert client.get("/api/v1/dashboard/stats", headers=h).status_code == 428
    r = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": initial_password, "new_password": new_password},
        headers=h,
    )
    assert r.status_code == 200, r.text
    # admin sem MFA → 428 com code mfa_required_setup
    r = client.get("/api/v1/dashboard/stats", headers=h)
    assert r.status_code == 428 and r.json()["code"] == "mfa_required_setup"
    setup = client.get("/api/v1/auth/mfa/setup", headers=h).json()
    code = pyotp.TOTP(setup["secret"]).now()
    r = client.post("/api/v1/auth/mfa/enable", json={"code": code}, headers=h)
    assert r.status_code == 200 and len(r.json()["recovery_codes"]) == 10, r.text
    # novo login exige MFA
    r = client.post("/api/v1/auth/login", json={"email": email, "password": new_password})
    ch = r.json()
    assert ch.get("mfa_required") is True
    r = client.post(
        "/api/v1/auth/mfa/verify",
        json={"mfa_token": ch["mfa_token"], "code": pyotp.TOTP(setup["secret"]).now()},
    )
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture(scope="session")
def admin(client):
    return admin_onboarding(client, "admin@asclepio.fiap", "Admin#Inicial2026", ADMIN_PASSWORD)


@pytest.fixture
def auditor(client):
    return _login(client, "auditor@asclepio.fiap")
