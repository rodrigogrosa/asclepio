import re

from asclepio_api.core.policies import DEFAULT_PASSWORD_POLICY, has_permission, permissions_for

API = "/api/v1"


def test_login_ok_and_me(client, medico):
    r = client.get(f"{API}/auth/me", headers=medico)
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "medico" and "workflows:decide" in body["permissions"]


def test_login_invalid(client):
    r = client.post(
        f"{API}/auth/login", json={"email": "dra.ana@asclepio.fiap", "password": "errada"}
    )
    assert r.status_code == 401


def test_unauthenticated(client):
    assert client.get(f"{API}/patients").status_code == 401
    assert (
        client.get(f"{API}/patients", headers={"Authorization": "Bearer abc.def.ghi"}).status_code
        == 401
    )


def test_lockout_after_failed_attempts(client):
    for _ in range(5):
        client.post(
            f"{API}/auth/login", json={"email": "dr.marcos@asclepio.fiap", "password": "errada"}
        )
    r = client.post(
        f"{API}/auth/login", json={"email": "dr.marcos@asclepio.fiap", "password": "Asclepio@2026"}
    )
    assert r.status_code == 423
    assert "bloqueada" in r.json()["detail"].lower()


def test_rbac_matrix():
    assert has_permission("admin", "anything:here")
    assert has_permission("medico", "workflows:decide")
    assert not has_permission("enfermagem", "workflows:decide")
    assert not has_permission("auditor", "patients:read")
    assert has_permission("auditor", "audit:read")
    assert "audit:read" in permissions_for("admin")


def test_password_policy():
    assert DEFAULT_PASSWORD_POLICY.validate("Asclepio@2026") == []
    probs = DEFAULT_PASSWORD_POLICY.validate("abc")
    assert len(probs) >= 3


def test_auditor_cannot_read_patients(client, auditor):
    assert client.get(f"{API}/patients", headers=auditor).status_code == 403


def test_security_headers_and_request_id(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.headers["x-content-type-options"] == "nosniff"
    assert re.fullmatch(r"[0-9a-f]{16}", r.headers["x-request-id"])
    assert "frame-ancestors" in r.headers["content-security-policy"]


def test_logout_audited(client, auditor):
    tok = client.post(
        f"{API}/auth/login", json={"email": "dra.ana@asclepio.fiap", "password": "Asclepio@2026"}
    ).json()
    h = {"Authorization": f"Bearer {tok['access_token']}"}
    assert client.post(f"{API}/auth/logout", headers=h).json()["ok"] is True
    r = client.get(f"{API}/audit?action=auth.logout", headers=auditor)
    assert r.json()["total"] >= 1
