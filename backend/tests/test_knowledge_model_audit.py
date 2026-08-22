import asyncio

from sqlalchemy import select, update

API = "/api/v1"


def test_documents_and_search(client, medico):
    docs = client.get(f"{API}/knowledge/documents", headers=medico).json()
    assert len(docs) > 100 and {d["doc_type"] for d in docs} >= {"protocolo", "modelo", "faq"}
    one = client.get(f"{API}/knowledge/documents/PROT-001", headers=medico).json()
    assert one["content"].startswith("---") and one["chunks"] > 3
    s = client.post(
        f"{API}/knowledge/search", json={"query": "sepse lactato", "k": 3}, headers=medico
    ).json()
    assert len(s["results"]) >= 1 and "score" in s["results"][0]


def test_reindex_admin_only(client, medico, admin):
    assert client.post(f"{API}/knowledge/reindex", headers=medico).status_code == 403
    r = client.post(f"{API}/knowledge/reindex", headers=admin).json()
    assert r["chunks"] > 100


def test_model_info_and_switch(client, medico, admin):
    assert (
        client.get(f"{API}/model/info", headers=medico).status_code == 403
    )  # IA & Modelos: só admin
    info = client.get(f"{API}/model/info", headers=admin).json()
    assert info["active"]["provider"] == "fake"
    assert (
        client.post(f"{API}/model/switch", json={"model": "x"}, headers=medico).status_code == 403
    )
    assert (
        client.post(
            f"{API}/model/switch", json={"model": "fake-clinical"}, headers=admin
        ).status_code
        == 200
    )


def test_dashboard_per_role(client, medico, admin, auditor):
    d = client.get(f"{API}/dashboard/stats", headers=medico).json()
    assert d["patients"] >= 20 and "risk_distribution" in d
    assert d["model"] is None and d["guardrail_blocks_today"] is None  # médico não vê IA/sistema
    assert "pending_approvals" in d["my_work"]
    a = client.get(f"{API}/dashboard/stats", headers=admin).json()
    assert a["model"]["provider"] == "fake" and isinstance(a["guardrail_blocks_today"], int)
    au = client.get(f"{API}/dashboard/stats", headers=auditor).json()
    assert au["my_work"] is None and au["model"] is None


def test_public_config_and_catalogs(client, medico, admin):
    cfg = client.get(f"{API}/public/config").json()
    assert (
        cfg["hospital_name"] and cfg["demo_mode"] is True and "admin" in cfg["mfa_required_roles"]
    )
    specs = client.get(f"{API}/catalog/specialties", headers=medico).json()
    assert len(specs) >= 25 and all("professionals_count" in s for s in specs)
    sectors = client.get(f"{API}/catalog/sectors", headers=medico).json()
    assert any(s["name"] == "Pronto-Socorro" for s in sectors)
    # médico não gerencia catálogos
    assert (
        client.post(f"{API}/catalog/specialties", json={"name": "Nova"}, headers=medico).status_code
        == 403
    )
    r = client.post(
        f"{API}/catalog/specialties",
        json={"name": "Medicina do Sono", "code": "SON"},
        headers=admin,
    )
    assert r.status_code == 201
    sid = r.json()["id"]
    assert (
        client.post(
            f"{API}/catalog/specialties", json={"name": "medicina do sono"}, headers=admin
        ).status_code
        == 409
    )
    assert (
        client.patch(
            f"{API}/catalog/specialties/{sid}", json={"active": False}, headers=admin
        ).json()["active"]
        is False
    )
    assert client.delete(f"{API}/catalog/specialties/{sid}", headers=admin).json()["ok"]
    r = client.post(
        f"{API}/catalog/sectors", json={"name": "Maternidade", "kind": "internacao"}, headers=admin
    )
    assert r.status_code == 201
    assert (
        client.post(
            f"{API}/catalog/sectors", json={"name": "X", "kind": "invalido"}, headers=admin
        ).status_code
        == 422
    )


def test_health_and_metrics(client):
    h = client.get("/health").json()
    assert h["status"] == "ok" and h["vectorstore"]["chunks"] > 100
    assert "http_request" in client.get("/metrics").text


def test_audit_chain_verify_and_tamper_detection(client, auditor, admin):
    page = client.get(f"{API}/audit?limit=10", headers=auditor).json()
    assert page["total"] > 10 and page["items"][0]["hash"]
    assert client.get(f"{API}/audit/verify", headers=auditor).json()["ok"] is True
    assert client.get(f"{API}/audit/actions", headers=auditor).json()
    entry = client.get(f"{API}/audit/{page['items'][-1]['id']}", headers=auditor).json()
    assert entry["action"]

    # adultera um registro direto no banco → cadeia quebra
    from asclepio_api.db import models as m
    from asclepio_api.db.base import session_factory

    async def tamper():
        async with session_factory()() as s:
            first = (
                await s.execute(select(m.AuditLog).order_by(m.AuditLog.id).limit(1))
            ).scalar_one()
            await s.execute(
                update(m.AuditLog)
                .where(m.AuditLog.id == first.id)
                .values(action="auth.login_TAMPERED")
            )
            await s.commit()
            return first.id

    tampered_id = asyncio.run(tamper())
    v = client.get(f"{API}/audit/verify", headers=auditor).json()
    assert v["ok"] is False and v["broken_at"] == tampered_id
