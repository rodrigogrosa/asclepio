"""Mobilidade: cada regra e o encaixe dos geradores sintéticos com o gabarito."""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
from asclepio_multimodal.anomaly.mobility import detect_mobility_anomalies
from asclepio_multimodal.schemas import MobilityReading

START = datetime(2026, 8, 20, 6, 0)  # começa de manhã: 2 dias completos = 192 leituras


def rotina(n: int = 192, seed: int = 3, dia: float = 0.35) -> list[MobilityReading]:
    """Paciente normal: vira a cada ~90 min, mais ativo de dia que de noite."""
    rng = np.random.default_rng(seed)
    out, pos, left = [], "dorsal", 6
    for i in range(n):
        at = START + timedelta(minutes=15 * i)
        noite = at.hour >= 22 or at.hour < 6
        if left == 0:
            pos, left = ("lateral_esq" if pos == "dorsal" else "dorsal"), 6
        left -= 1
        a = abs(rng.normal(0.04, 0.03)) if noite else float(np.clip(rng.normal(dia, 0.08), 0.1, 1))
        out.append(MobilityReading(at=at, activity=min(a, 1.0), position=pos))
    return out


def com(rs, ini, fim, **campos):
    for i in range(ini, fim):
        rs[i] = rs[i].model_copy(update=campos)
    return rs


def achados(rs):
    r = detect_mobility_anomalies(rs)
    return {f.code.split(".")[1]: f for f in r.findings if f.severity != "info"}, r


def test_rotina_normal_nao_alerta():
    a, r = achados(rotina())
    assert a == {} and r.risk_level == "baixo"
    assert r.metrics["mudancas_de_posicao"] > 20


def test_imobilidade_duas_e_quatro_horas():
    a, _ = achados(com(rotina(), 20, 30, position="dorsal", activity=0.02))  # 10 leituras = 2,5 h
    assert (
        a["imobilidade"].severity == "atencao" and a["imobilidade"].evidence["duracao_min"] >= 150
    )
    a, _ = achados(com(rotina(), 20, 40, position="dorsal", activity=0.02))  # 5 h
    assert a["imobilidade"].severity == "critico"
    # 6 leituras (90 min) iguais é rotina
    assert "imobilidade" not in achados(com(rotina(), 20, 26, position="dorsal"))[0]


def test_queda_posicao_chao():
    a, r = achados(com(rotina(), 100, 103, position="chao", in_bed=False, activity=0.02))
    f = a["queda"]
    assert (
        f.severity == "critico"
        and f.evidence["duracao_min"] == 45
        and f.at == START + timedelta(minutes=1500)
    )
    assert r.risk_level == "critico" and r.metrics["quedas"] == 1


def test_saida_do_leito_apenas_a_noite():
    rs = rotina()
    noite = next(
        i for i in range(192) if (START + timedelta(minutes=15 * i)).hour == 2
    )  # 02h do dia 1
    a, _ = achados(com(rs, noite, noite + 2, position="em_pe", in_bed=False, activity=0.6))
    assert a["saida_leito_noturna"].evidence["hora"] == 2
    # a mesma saída às 10h não é alerta
    dia = next(i for i in range(192) if (START + timedelta(minutes=15 * i)).hour == 10)
    assert (
        "saida_leito_noturna"
        not in achados(com(rotina(), dia, dia + 2, position="em_pe", in_bed=False))[0]
    )


def test_agitacao_noturna_acima_da_linha_de_base_diurna():
    rs = rotina()
    for i, r in enumerate(rs):
        if r.at.hour >= 22 or r.at.hour < 6:
            rs[i] = r.model_copy(update={"activity": 0.7})
    a, _ = achados(rs)
    f = a["agitacao_noturna"]
    assert (
        f.evidence["atividade_noturna"] > f.evidence["mediana_diurna"] and f.severity == "critico"
    )


def test_queda_subita_de_atividade_diurna():
    rs = rotina()
    ini = next(i for i in range(60, 192) if (START + timedelta(minutes=15 * i)).hour == 13)
    a, _ = achados(com(rs, ini, ini + 12, activity=0.02))
    f = a["queda_atividade"]
    assert (
        f.evidence["atividade_2h"] < 0.35 * f.evidence["linha_de_base"]
        and f.evidence["z_robusto"] <= -3
    )


def test_padrao_diario_atipico_isolation_forest():
    rs = rotina(seed=5)
    ini = next(i for i in range(100, 192) if (START + timedelta(minutes=15 * i)).hour == 14)
    # 3 h seguidas fora do leito, agitadas e trocando de posição: nenhuma regra específica explica
    for k in range(12):
        pos = "em_pe" if k % 2 else "sentado"
        rs[ini + k] = rs[ini + k].model_copy(
            update={"activity": 0.95, "in_bed": False, "position": pos}
        )
    a, _ = achados(rs)
    assert "padrao_atipico" in a and a["padrao_atipico"].evidence["horas"] >= 2


def test_leituras_insuficientes_e_contrato():
    r = detect_mobility_anomalies(rotina()[:1])
    assert r.kind == "mobilidade" and r.warnings
    r = detect_mobility_anomalies(com(rotina(), 100, 103, position="chao", in_bed=False))
    for k in ("t", "activity", "position", "in_bed", "anomaly_index", "anomaly_at"):
        assert k in r.series
    assert len(r.series["t"]) == 192 and r.metrics["leituras"] == 192 and r.models
