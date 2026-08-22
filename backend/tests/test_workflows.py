API = "/api/v1"


def test_clinical_review_full_cycle(client, medico, enfermagem):
    r = client.post(
        f"{API}/workflows/clinical-review",
        json={"patient_id": 1, "reason": "Revisão do plantão"},
        headers=medico,
    )
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["status"] == "aguardando_aprovacao"
    nodes = [s["node"] for s in run["steps"]]
    for n in (
        "load_patient",
        "check_pending_exams",
        "triage_risk",
        "retrieve_protocols",
        "suggest_conduct",
        "validate_guardrails",
        "emit_alerts",
        "human_review",
    ):
        assert n in nodes
    res = run["result"]
    assert res["risk_level"] == "critico"  # cenário de sepse
    assert res["alerts"] and res["citations"] and res["llm_summary"]
    assert any(s["node"] == "emit_immediate_alerts" for s in run["steps"])
    assert res["suggestions"], "sugestões estruturadas parseadas da resposta"
    assert res["suggestions"][0]["priority"] in ("alta", "media", "baixa")

    # enfermagem não pode decidir
    d = client.post(
        f"{API}/workflows/runs/{run['run_id']}/decision",
        json={"approved": True},
        headers=enfermagem,
    )
    assert d.status_code == 403

    d = client.post(
        f"{API}/workflows/runs/{run['run_id']}/decision",
        json={"approved": True, "comment": "ok"},
        headers=medico,
    )
    assert d.status_code == 200, d.text
    done = d.json()
    assert done["status"] == "aprovado" and done["human_decision"]["approved"] is True
    assert [s["node"] for s in done["steps"]][-2:] == ["human_review", "finalize"]
    # segunda decisão → 409
    assert (
        client.post(
            f"{API}/workflows/runs/{run['run_id']}/decision",
            json={"approved": True},
            headers=medico,
        ).status_code
        == 409
    )


def test_rejected_run_acknowledges_alerts(client, medico):
    run = client.post(
        f"{API}/workflows/clinical-review", json={"patient_id": 5}, headers=medico
    ).json()
    assert run["status"] == "aguardando_aprovacao"
    done = client.post(
        f"{API}/workflows/runs/{run['run_id']}/decision",
        json={"approved": False, "comment": "discordo"},
        headers=medico,
    ).json()
    assert done["status"] == "rejeitado"
    open_alerts = client.get(f"{API}/alerts?patient_id=5&open_only=true", headers=medico).json()
    assert all(a["run_id"] != run["run_id"] for a in open_alerts)


def test_low_risk_patient_no_immediate_alert(client, medico):
    rows = client.get(f"{API}/patients?risk=baixo", headers=medico).json()
    run = client.post(
        f"{API}/workflows/clinical-review", json={"patient_id": rows[0]["id"]}, headers=medico
    ).json()
    assert run["result"]["risk_level"] == "baixo"
    assert not any(s["node"] == "emit_immediate_alerts" for s in run["steps"])


def test_runs_listing_and_graph(client, medico, enfermagem):
    runs = client.get(f"{API}/workflows/runs", headers=enfermagem).json()
    assert runs and runs[0]["run_id"]
    one = client.get(f"{API}/workflows/runs/{runs[0]['run_id']}", headers=medico).json()
    assert one["steps"]
    g = client.get(f"{API}/workflows/graph", headers=medico).json()
    assert "human_review" in g["mermaid"] and len(g["nodes"]) == 10
    assert client.get(f"{API}/workflows/runs/nao-existe", headers=medico).status_code == 404


def test_alert_ack(client, medico):
    alerts = client.get(f"{API}/alerts", headers=medico).json()
    assert alerts
    a = client.post(f"{API}/alerts/{alerts[0]['id']}/ack", headers=medico).json()
    assert a["acknowledged_by"]
