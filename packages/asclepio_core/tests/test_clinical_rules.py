from datetime import datetime, timedelta

from asclepio_core.clinical_rules import (
    assess_risk,
    evaluate_labs,
    is_overdue,
    news2,
    parse_number,
    qsofa,
    suggest_protocols,
)


def test_parse_number_pt_br():
    assert parse_number("3,4") == 3.4
    assert parse_number("19800 /mm³") == 19800
    assert parse_number("Leucócitos 19.800") is None or isinstance(
        parse_number("Leucócitos 19.800"), float
    )
    assert parse_number(None) is None


def test_evaluate_labs_critical_and_attention():
    exams = [
        {"name": "Potássio", "result_value": "6,4", "unit": "mmol/L", "status": "concluido"},
        {"name": "Lactato arterial", "result_value": "3,1", "status": "concluido"},
        {"name": "Glicemia capilar", "result_value": "95", "status": "concluido"},
        {"name": "Creatinina", "result_value": None, "status": "pendente"},
    ]
    f = evaluate_labs(exams)
    kinds = {(x.exam, x.severity) for x in f}
    assert ("Potássio", "critico") in kinds
    assert ("Lactato arterial", "atencao") in kinds
    assert all(x.exam != "Glicemia capilar" for x in f)


def test_qsofa_and_news2():
    v = {"hr": 118, "sbp": 88, "dbp": 50, "rr": 26, "temp_c": 39.2, "spo2": 90, "gcs": 14}
    assert qsofa(v)[0] == 3
    assert news2(v)[0] >= 7
    assert qsofa({"hr": 70, "sbp": 120, "rr": 14, "gcs": 15})[0] == 0


def test_is_overdue():
    now = datetime(2026, 8, 21, 12, 0)
    assert is_overdue({"status": "pendente", "due_at": (now - timedelta(hours=1)).isoformat()}, now)
    assert not is_overdue(
        {"status": "pendente", "due_at": (now + timedelta(hours=1)).isoformat()}, now
    )
    assert not is_overdue(
        {"status": "concluido", "due_at": (now - timedelta(hours=5)).isoformat()}, now
    )
    assert is_overdue({"status": "atrasado", "due_at": None}, now)


def test_assess_risk_levels():
    crit = assess_risk(
        {"hr": 118, "sbp": 88, "rr": 26, "temp_c": 39.2, "spo2": 90, "gcs": 14},
        [{"name": "Lactato", "result_value": "4,5", "status": "concluido"}],
        "pneumonia com sepse",
        67,
    )
    assert crit.level == "critico" and "PROT-001" in crit.protocol_hints
    low = assess_risk(
        {"hr": 72, "sbp": 120, "rr": 14, "temp_c": 36.5, "spo2": 98, "gcs": 15},
        [],
        "hérnia inguinal",
        40,
    )
    assert low.level == "baixo" and low.score == 0


def test_suggest_protocols():
    assert "PROT-003" in suggest_protocols("AVC isquêmico com hemiparesia")
    assert "PROT-012" in suggest_protocols("hipercalemia em LRA")
