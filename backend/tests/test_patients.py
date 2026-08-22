import re

API = "/api/v1"


def test_list_patients_sorted_by_risk(client, medico):
    r = client.get(f"{API}/patients", headers=medico)
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) >= 20
    assert rows[0]["risk_level"] == "critico"
    assert {"id", "mrn", "risk_level", "pending_exams_count", "overdue_exams_count"} <= set(rows[0])


def test_detail_and_filters(client, medico):
    rows = client.get(f"{API}/patients?risk=critico", headers=medico).json()
    assert rows and all(r["risk_level"] == "critico" for r in rows)
    d = client.get(f"{API}/patients/{rows[0]['id']}", headers=medico).json()
    assert d["vitals"] and d["exams"] and d["notes"]
    assert client.get(f"{API}/patients/99999", headers=medico).status_code == 404


def test_context_has_no_pii(client, medico):
    p = client.get(f"{API}/patients/1", headers=medico).json()
    ctx = client.get(f"{API}/patients/1/context", headers=medico).json()
    text = ctx["anonymized_context"]
    assert ctx["pii_redacted"] > 0
    assert p["name"] not in text
    assert p["name"].split()[0] not in text
    assert not re.search(r"\d{3}\.\d{3}\.\d{3}-\d{2}", text)  # CPF
    assert not re.search(r"\(\d{2}\)\s?\d{4,5}-\d{4}", text)  # telefone
    assert "Avaliação de risco" in text
    assert "Sinais vitais" in text
