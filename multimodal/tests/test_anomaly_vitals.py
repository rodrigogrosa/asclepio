"""Sinais vitais: cada regra do detector em séries sintéticas, antiflood e lote."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pytest
from asclepio_multimodal.anomaly import LIVE_SOURCES, load_live_source
from asclepio_multimodal.anomaly.synthetic import synthetic_onset_index, synthetic_vitals_stream
from asclepio_multimodal.anomaly.vitals import OnlineVitalsDetector, detect_vital_anomalies
from asclepio_multimodal.schemas import VitalSample

T0 = datetime(2026, 8, 21, 8, 0)
STABLE = {"hr": 76.0, "sbp": 122.0, "dbp": 74.0, "rr": 16.0, "spo2": 97.0, "temp_c": 36.7}


def series(n: int, seed: int = 1, **over) -> list[VitalSample]:
    """n amostras/min estáveis com ruído pequeno; ``over[campo]`` = função(i) -> delta somado ao valor."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n):
        v = {}
        for k, base in STABLE.items():
            noise = rng.normal(
                0, {"hr": 1.5, "sbp": 2, "dbp": 1.5, "rr": 0.5, "spo2": 0.4, "temp_c": 0.04}[k]
            )
            v[k] = base + noise + (over[k](i) if k in over else 0.0)
        out.append(VitalSample(at=T0 + timedelta(minutes=i), **v))
    return out


def run(samples, **kw):
    det = OnlineVitalsDetector(**kw)
    found = [(i, f) for i, s in enumerate(samples) for f in det.update(s)]
    return det, found


def codes(found):
    return {f.code for _, f in found}


def test_estavel_nao_gera_alerta():
    det, found = run(series(180))
    assert found == []
    assert det.score < 0.3


def test_limite_spo2_critico_com_evidencia():
    s = series(60, spo2=lambda i: -9 if i >= 40 else 0)  # 97 -> 88
    _, found = run(s, methods={"limiar"})
    f = next(f for _, f in found if f.code == "sinais.spo2_baixa" and f.severity == "critico")
    assert f.modality == "sinais" and f.at is not None and f.evidence["valor"] <= 91
    assert f.recommendation


def test_limites_pam_derivada_quando_nao_medida():
    # PAS 85 / PAD 50 -> PAM ≈ 61.7 (abaixo de 65): atenção; não há PAM medida
    s = series(30, sbp=lambda i: -37, dbp=lambda i: -24)
    _, found = run(s, methods={"limiar"})
    assert "sinais.pam_baixa" in codes(found)
    assert "sinais.pas_baixa" in codes(found)


def test_indice_de_choque():
    s = series(30, hr=lambda i: 40, sbp=lambda i: -14)  # FC 116 / PAS 108 -> 1,07
    _, found = run(s, methods={"limiar"})
    assert "sinais.indice_choque" in codes(found)


def test_zscore_robusto_mudanca_brusca():
    s = series(60, hr=lambda i: 45 if 40 <= i < 46 else 0)
    _, found = run(s, methods={"zscore"})
    assert any(f.code == "sinais.mudanca_brusca_hr" for _, f in found)
    assert all(40 <= i <= 46 for i, _ in found)
    # sem o salto, nada
    assert run(series(60), methods={"zscore"})[1] == []


def test_zscore_ignora_artefato_de_uma_amostra():
    s = series(60, hr=lambda i: 60 if i == 40 else 0)
    assert run(s, methods={"zscore"})[1] == []


def test_deriva_cusum_antecipa_o_limite():
    # PAM cai ~30 mmHg em 60 min a partir do minuto 100: a deriva avisa antes do limite de 65
    s = series(
        200,
        sbp=lambda i: -min(max(i - 100, 0), 60) * 0.5 * 1.5,
        dbp=lambda i: -min(max(i - 100, 0), 60) * 0.5,
    )
    _, drift = run(s, methods={"deriva"})
    _, limit = run(s, methods={"limiar"})
    d = [i for i, f in drift if f.code in ("sinais.deriva_map", "sinais.deriva_sbp")]
    p = [i for i, f in limit if f.code in ("sinais.pam_baixa", "sinais.pas_baixa")]
    assert d, "a deriva deveria ser detectada"
    assert d[0] >= 100
    assert not p or d[0] < p[0]
    assert all(f.severity == "atencao" for _, f in drift)  # deriva só antecipa


def test_deriva_spo2_progressiva():
    s = series(200, spo2=lambda i: -min(max(i - 100, 0), 50) * 0.16)  # -8 pontos em 50 min
    _, found = run(s, methods={"deriva"})
    assert "sinais.deriva_spo2" in codes(found)


def test_iforest_combinacao_fc_pam_dentro_dos_limites():
    # FC +22 (98 bpm), PAS -26 (96 -> alerta de PAS apenas leve) e FR +5: cada uma isolada é discreta
    s = series(
        150,
        hr=lambda i: 22 if i >= 90 else 0,
        sbp=lambda i: -24 if i >= 90 else 0,
        dbp=lambda i: -14 if i >= 90 else 0,
        rr=lambda i: 5 if i >= 90 else 0,
    )
    _, found = run(s, methods={"iforest"})
    f = next(f for i, f in found if f.code == "sinais.multivariada")
    assert f.evidence["sinais_adversos"] >= 2 and f.evidence["escore_iforest"] >= 0.6
    assert run(series(150), methods={"iforest"})[1] == []


def test_antiflood_duracao_minima_histerese_e_cooldown():
    # SpO2 oscila 90/95 a cada 3 min por 1 h: sem filtro vira dezenas de alertas
    s = series(100, spo2=lambda i: -7 if (i // 3) % 2 == 0 and i >= 20 else 0)
    _, raw = run(s, methods={"limiar"}, antiflood=False)
    _, calm = run(s, methods={"limiar"})
    spo2_raw = [f for _, f in raw if f.code == "sinais.spo2_baixa"]
    spo2_calm = [f for _, f in calm if f.code == "sinais.spo2_baixa"]
    assert len(spo2_raw) > 20
    assert 1 <= len(spo2_calm) <= 2


def test_antiflood_escalona_atencao_para_critico():
    s = series(80, spo2=lambda i: -5 if 30 <= i < 45 else -10 if i >= 45 else 0)  # 92 -> 87
    _, found = run(s, methods={"limiar"})
    sev = [f.severity for _, f in found if f.code == "sinais.spo2_baixa"]
    assert sev == ["atencao", "critico"]


def test_cooldown_rearma_depois_de_recuperar():
    # dois episódios de hipoxemia separados por 60 min normais: dois alertas
    s = series(200, spo2=lambda i: -9 if (30 <= i < 50 or 130 <= i < 150) else 0)
    _, found = run(s, methods={"limiar"})
    assert (
        len([1 for _, f in found if f.code == "sinais.spo2_baixa" and f.severity == "critico"]) == 2
    )


def test_amostras_muito_proximas_sao_ignoradas():
    det = OnlineVitalsDetector()
    det.update(VitalSample(at=T0, **STABLE))
    assert det.update(VitalSample(at=T0 + timedelta(seconds=5), **{**STABLE, "spo2": 70})) == []
    assert det.n_samples == 1


def test_campos_ausentes_nao_quebram():
    det = OnlineVitalsDetector()
    for i in range(80):
        det.update(VitalSample(at=T0 + timedelta(minutes=i), hr=80, spo2=None if i % 3 else 97))
    assert 0 <= det.score <= 1


def test_score_sobe_na_deterioracao():
    det, _ = run(synthetic_vitals_stream("sepse", start=T0))
    assert det.score > 0.7
    assert det.news2_score >= 5


def test_detect_vital_anomalies_sepse_contrato_e_gabarito():
    ss = synthetic_vitals_stream("sepse", start=T0)
    r = detect_vital_anomalies(ss)
    onset = T0 + timedelta(minutes=synthetic_onset_index("sepse"))
    assert r.kind == "sinais" and r.severity == "critico" and r.risk_level in ("alto", "critico")
    assert r.findings and all(f.at is not None and f.modality == "sinais" for f in r.findings)
    assert min(f.at for f in r.findings) >= onset  # nenhum alerta antes da anomalia começar
    assert min(f.at for f in r.findings) <= onset + timedelta(minutes=20)
    for k in (
        "t",
        "hr",
        "sbp",
        "dbp",
        "map",
        "rr",
        "spo2",
        "temp_c",
        "anomaly_score",
        "anomaly_index",
        "anomaly_at",
    ):
        assert k in r.series
    n = len(ss)
    assert all(len(r.series[k]) == n for k in ("t", "hr", "map", "anomaly_score", "anomaly_flag"))
    assert r.series["anomaly_index"] and r.models and r.metrics["alertas"] == len(r.findings)


def test_detect_vital_anomalies_estavel_e_vazio():
    r = detect_vital_anomalies(synthetic_vitals_stream("estavel", start=T0))
    assert r.findings == [] and r.risk_level == "baixo"
    assert detect_vital_anomalies([]).warnings


def test_dessaturacao_detectada_logo_apos_o_inicio():
    ss = synthetic_vitals_stream("dessaturacao", start=T0)
    r = detect_vital_anomalies(ss)
    onset = T0 + timedelta(minutes=synthetic_onset_index("dessaturacao"))
    spo2 = [f for f in r.findings if "spo2" in f.code]
    assert spo2 and min(f.at for f in spo2) - onset <= timedelta(minutes=10)


def test_detector_e_deterministico():
    a = detect_vital_anomalies(synthetic_vitals_stream("sepse", start=T0, n=150))
    b = detect_vital_anomalies(synthetic_vitals_stream("sepse", start=T0, n=150))
    assert [(f.code, f.at) for f in a.findings] == [(f.code, f.at) for f in b.findings]
    assert a.series["anomaly_score"] == b.series["anomaly_score"]


def test_fontes_ao_vivo():
    assert LIVE_SOURCES and all(isinstance(v, str) for v in LIVE_SOURCES.values())
    assert len(load_live_source("sintetico:sepse", start=T0)) == 240
    with pytest.raises(ValueError):
        load_live_source("nao-existe:x", start=T0)
    with pytest.raises(ValueError):
        load_live_source("sintetico:inexistente", start=T0)
    with pytest.raises(ValueError):
        load_live_source("physionet:abc", start=T0)
