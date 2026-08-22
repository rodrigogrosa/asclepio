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


@pytest.fixture(scope="session")
def medico(client):
    return _login(client, "dra.ana@asclepio.fiap")


@pytest.fixture(scope="session")
def enfermagem(client):
    return _login(client, "enf.carla@asclepio.fiap")


@pytest.fixture(scope="session")
def admin(client):
    return _login(client, "admin@asclepio.fiap")


@pytest.fixture(scope="session")
def auditor(client):
    return _login(client, "auditor@asclepio.fiap")
