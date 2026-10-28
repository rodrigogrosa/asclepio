"""Geradores sintéticos: determinismo, gabarito e encaixe com os 24 pacientes de asclepio_core."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from asclepio_core.synthetic import DEFAULT_NOW, generate_patients
from asclepio_multimodal.anomaly import physionet as pn
from asclepio_multimodal.anomaly.mobility import detect_mobility_anomalies
from asclepio_multimodal.anomaly.prescriptions import detect_prescription_anomalies
from asclepio_multimodal.anomaly.synthetic import (
    MOBILITY_TRUTH,
    PRESCRIPTION_TRUTH,
    generate_mobility,
    generate_prescription_history,
    parse_dose,
    synthetic_onset,
    synthetic_onset_index,
    synthetic_vitals_stream,
)

NOW = DEFAULT_NOW


@pytest.fixture(scope="module")
def pacientes():
    return generate_patients(now=NOW)


def test_vitais_sinteticos_deterministicos_e_gabarito():
    a = synthetic_vitals_stream("sepse", start=NOW)
    assert a == synthetic_vitals_stream("sepse", start=NOW)
    assert len(a) == 240 and a[1].at - a[0].at == timedelta(seconds=60)
    assert (
        synthetic_onset_index("estavel") is None and synthetic_onset("estavel", start=NOW) is None
    )
    assert synthetic_onset("sepse", start=NOW) == NOW + timedelta(minutes=120)
    # sepse: FC sobe, PAS cai, SpO2 cai depois do início; estável não muda
    pre, pos = a[:100], a[-20:]
    m = lambda xs, k: float(np.mean([getattr(x, k) for x in xs]))  # noqa: E731
    assert (
        m(pos, "hr") > m(pre, "hr") + 25
        and m(pos, "sbp") < m(pre, "sbp") - 25
        and m(pos, "spo2") < m(pre, "spo2") - 4
    )
    est = synthetic_vitals_stream("estavel", start=NOW, n=120, step_s=30)
    assert abs(m(est[:30], "hr") - m(est[-30:], "hr")) < 4 and est[1].at - est[0].at == timedelta(
        seconds=30
    )
    with pytest.raises(ValueError):
        synthetic_vitals_stream("outro", start=NOW)


def test_historico_de_prescricao_deterministico_e_ordenado(pacientes):
    for p in pacientes:
        a = generate_prescription_history(p, now=NOW)
        assert a == generate_prescription_history(p, now=NOW)
        assert a == sorted(a, key=lambda e: e.at) and all(e.at <= NOW for e in a)
    sepse = next(p for p in pacientes if p["scenario"] == "sepse_pac")
    assert any("iperacilina" in e.drug for e in generate_prescription_history(sepse, now=NOW))


def test_mobilidade_sintetica_deterministica_e_bem_formada(pacientes):
    p = pacientes[0]
    a = generate_mobility(p, now=NOW)
    assert a == generate_mobility(p, now=NOW)
    assert len(a) == 192 and a[-1].at == NOW and a[1].at - a[0].at == timedelta(minutes=15)
    assert len(generate_mobility(p, now=NOW, hours=12)) == 48
    assert all(0 <= r.activity <= 1 for r in a)
    assert a != generate_mobility(pacientes[1], now=NOW)


def test_geradores_aceitam_banco_reconstruido():
    """O backend passa um dict mínimo (datas como datetime ou ISO, só campos básicos)."""
    p = {
        "mrn": "X1",
        "name": "Fulano",
        "age": 70,
        "sex": "M",
        "scenario": "controle_glicemico",
        "allergies": [],
        "weight_kg": 80,
        "admission_date": NOW - timedelta(days=2),
        "medications": [
            {
                "name": "Insulina glargina",
                "dose": "14 UI",
                "route": "SC",
                "frequency": "noite",
                "started_at": (NOW - timedelta(days=1)).isoformat(),
                "status": "ativo",
            },
            {
                "name": "Cefalexina",
                "dose": "1 g",
                "route": "VO",
                "frequency": "6/6h",
                "started_at": NOW - timedelta(days=1),
                "status": "ativo",
            },
        ],
    }
    ev = generate_prescription_history(p, now=NOW)
    assert any(
        e.action == "ajuste" and e.drug == "Insulina glargina" and e.dose_value == 36 for e in ev
    )
    assert generate_mobility({"mrn": "Y"}, now=NOW, hours=24)
    assert generate_prescription_history({"mrn": "Z"}, now=NOW) == []
    # now com fuso horário e datas ingênuas no banco
    from datetime import UTC

    assert generate_prescription_history(p, now=NOW.replace(tzinfo=UTC))


def test_parse_dose():
    assert parse_dose("2 g") == (2.0, "g")
    assert parse_dose("1.000 mL") == (1000.0, "mL")
    assert parse_dose("0,1 UI/kg/h") == (0.1, "UI/kg/h")
    assert parse_dose("875/125 mg") == (875.0, "mg")
    assert parse_dose("300 mg ataque, 75 mg/dia") == (300.0, "mg")
    assert parse_dose("conforme glicemia") == (None, "")
    assert parse_dose(None) == (None, "")


@pytest.mark.parametrize("hora", [(8, 0), (14, 30)])
def test_pacientes_sinteticos_batem_com_o_gabarito(hora):
    now = NOW.replace(hour=hora[0], minute=hora[1])
    for p in generate_patients(now=now):
        sc = p["scenario"]
        rx = detect_prescription_anomalies(
            generate_prescription_history(p, now=now),
            allergies=p["allergies"],
            weight_kg=p["weight_kg"],
        )
        got = {f.code for f in rx.findings if f.severity != "info"}
        assert got == PRESCRIPTION_TRUTH.get(sc, set()), (sc, "prescricao")
        mob = detect_mobility_anomalies(generate_mobility(p, now=now))
        got = {f.code for f in mob.findings if f.severity != "info"}
        assert got == MOBILITY_TRUTH.get(sc, set()), (sc, "mobilidade")


def test_physionet_sem_rede():
    for ruim in ("abc", "301", "1010", "physionet:99"):
        with pytest.raises(ValueError):
            pn.record_id(ruim)
    assert pn.record_id("physionet:202") == "202" and pn.record_id("challenge-2009/101") == "101"
    # AHE: ≥ 90 % de 30 PAM consecutivas ≤ 60
    m = np.concatenate([np.full(50, 80.0), np.full(40, 55.0), np.full(20, 75.0)])
    assert pn.ahe_onset_index(m) == 50
    m2 = np.concatenate([np.full(50, 80.0), np.full(20, 55.0), np.full(40, 75.0)])
    assert pn.ahe_onset_index(m2) is None
    assert pn.ahe_onset_index(m, from_index=60) == 60
    n = 6
    data = {"t_min": np.arange(n, dtype=float), **{k: np.full(n, 70.0) for k in pn.CHANNELS}}
    data["spo2"][2] = np.nan
    ss = pn.to_samples(data, start=NOW)
    assert len(ss) == 6 and ss[2].spo2 is None and ss[3].at == NOW + timedelta(minutes=3)
    x = np.concatenate([np.full(60, 80.0), np.full(60, np.nan), np.full(60, 70.0)])
    agg = pn._agg_minute(x)
    assert agg[0] == 80 and np.isnan(agg[1]) and agg[2] == 70 and len(agg) == 3
    assert isinstance(NOW, datetime)
