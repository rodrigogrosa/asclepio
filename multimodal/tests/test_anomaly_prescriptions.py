"""Prescrições: cada regra de alteração inesperada."""

from __future__ import annotations

from datetime import datetime, timedelta

from asclepio_multimodal.anomaly.prescriptions import detect_prescription_anomalies, match_drug
from asclepio_multimodal.schemas import PrescriptionEvent

T0 = datetime(2026, 8, 20, 8, 0)


def ev(
    h: float,
    drug: str,
    dose: float | None = None,
    unit: str = "mg",
    freq: str = "12/12h",
    action: str = "inicio",
    note: str | None = None,
    route: str = "VO",
) -> PrescriptionEvent:
    return PrescriptionEvent(
        at=T0 + timedelta(hours=h),
        drug=drug,
        dose_value=dose,
        dose_unit=unit,
        route=route,
        frequency=freq,
        action=action,
        note=note,
    )


def got(events, **kw):
    r = detect_prescription_anomalies(events, **kw)
    return {(f.code.split(".")[1], f.severity) for f in r.findings}, r


def test_salto_de_dose_alta_vigilancia_dobra_e_cinquenta_por_cento():
    s, _ = got(
        [
            ev(0, "Insulina glargina", 14, "UI", "noite", route="SC"),
            ev(10, "Insulina glargina", 36, "UI", "noite", "ajuste", route="SC"),
        ]
    )
    assert ("salto_dose", "critico") in s
    s, _ = got(
        [
            ev(0, "Insulina glargina", 20, "UI", "noite", route="SC"),
            ev(10, "Insulina glargina", 32, "UI", "noite", "ajuste", route="SC"),
        ]
    )  # +60 %
    assert ("salto_dose", "atencao") in s
    s, _ = got(
        [
            ev(0, "Insulina glargina", 20, "UI", "noite", route="SC"),
            ev(10, "Insulina glargina", 24, "UI", "noite", "ajuste", route="SC"),
        ]
    )  # +20 %
    assert not any(c == "salto_dose" for c, _ in s)


def test_salto_em_medicamento_comum_so_a_partir_de_2x():
    base = [ev(0, "Furosemida", 40, "mg", "8/8h", route="EV")]
    assert not any(
        c == "salto_dose"
        for c, _ in got([*base, ev(9, "Furosemida", 60, "mg", "8/8h", "ajuste")])[0]
    )
    assert ("salto_dose", "atencao") in got(
        [*base, ev(9, "Furosemida", 120, "mg", "8/8h", "ajuste")]
    )[0]


def test_reducao_abrupta_de_alta_vigilancia():
    s, _ = got(
        [
            ev(0, "Enoxaparina", 80, "mg", "12/12h"),
            ev(30, "Enoxaparina", 30, "mg", "12/12h", "ajuste"),
        ]
    )
    assert any(c == "salto_dose" for c, _ in s)


def test_dose_acima_da_maxima_diaria():
    s, r = got([ev(0, "Dipirona", 1, "g", "4/4h")])  # 6 g/dia
    assert ("dose_maxima", "critico") in s
    f = r.findings[0]
    assert (
        f.evidence["dose_diaria"] == 6000
        and f.evidence["maximo_diario"] == 4000
        and "Bula" in f.description
    )
    assert got([ev(0, "Dipirona", 1, "g", "6/6h")])[0] == set()  # 4 g/dia exatos: ok
    assert got([ev(0, "Paracetamol", 750, "mg", "6/6h")])[0] == set()


def test_dose_maxima_por_kg_usa_o_peso():
    ordens = [ev(0, "Enoxaparina", 1.5, "mg/kg", "12/12h", route="SC")]  # 3 mg/kg/dia
    assert any(c == "dose_maxima" for c, _ in got(ordens, weight_kg=80)[0])
    assert got([ev(0, "Enoxaparina", 1, "mg/kg", "12/12h", route="SC")], weight_kg=80)[0] == set()


def test_suspensao_abrupta_de_anticoagulante():
    base = ev(-72, "Apixabana", 2.5, "mg", "12/12h")
    assert ("suspensao_abrupta", "critico") in got(
        [base, ev(0, "Apixabana", 2.5, "mg", "12/12h", "suspensao")]
    )[0]
    # trocado por outro anticoagulante em até 12 h, ou justificado: não alerta
    troca = [
        base,
        ev(0, "Apixabana", 2.5, "mg", "12/12h", "suspensao"),
        ev(2, "Enoxaparina", 40, "mg", "1x/dia"),
    ]
    assert not any(c == "suspensao_abrupta" for c, _ in got(troca)[0])
    just = [
        base,
        ev(0, "Apixabana", 2.5, "mg", "12/12h", "suspensao", note="Suspenso por alta hospitalar"),
    ]
    assert not any(c == "suspensao_abrupta" for c, _ in got(just)[0])


def test_suspensao_de_antibiotico_antes_do_curso():
    cedo = [
        ev(0, "Amoxicilina-clavulanato", 875, "mg", "12/12h"),
        ev(24, "Amoxicilina-clavulanato", 875, "mg", "12/12h", "suspensao"),
    ]
    assert ("suspensao_abrupta", "atencao") in got(cedo)[0]
    completo = [
        ev(0, "Amoxicilina-clavulanato", 875, "mg", "12/12h"),
        ev(24 * 7, "Amoxicilina-clavulanato", 875, "mg", "12/12h", "suspensao"),
    ]
    assert got(completo)[0] == set()


def test_suspensao_de_corticoide_prolongado_e_betabloqueador_sem_desmame():
    cort = [
        ev(0, "Prednisona", 40, "mg", "1x/dia"),
        ev(24 * 10, "Prednisona", 40, "mg", "1x/dia", "suspensao"),
    ]
    assert ("suspensao_abrupta", "atencao") in got(cort)[0]
    # desmame: dose final <= 50 % do pico
    desm = [
        ev(0, "Prednisona", 40, "mg", "1x/dia"),
        ev(24 * 9, "Prednisona", 15, "mg", "1x/dia", "ajuste"),
        ev(24 * 10, "Prednisona", 15, "mg", "1x/dia", "suspensao"),
    ]
    assert not any(c == "suspensao_abrupta" for c, _ in got(desm)[0])
    bb = [
        ev(0, "Metoprolol", 25, "mg", "12/12h"),
        ev(48, "Metoprolol", 25, "mg", "12/12h", "suspensao"),
    ]
    assert ("suspensao_abrupta", "atencao") in got(bb)[0]


def test_alergia_por_classe_direta_e_cruzada():
    s, r = got(
        [ev(0, "Piperacilina-tazobactam", 4.5, "g", "6/6h", route="EV")],
        allergies=["Penicilina (urticária)"],
    )
    assert ("alergia", "critico") in s and "Penicilina" in r.findings[0].description
    assert ("alergia", "critico") in got(
        [ev(0, "Dipirona", 1, "g", "6/6h")], allergies=["Dipirona (angioedema)"]
    )[0]
    assert ("alergia", "critico") in got(
        [ev(0, "SMX-TMP (Bactrim)", 800, "mg", "12/12h")], allergies=["Sulfa (rash)"]
    )[0]
    assert ("alergia", "critico") in got(
        [ev(0, "Enoxaparina", 40, "mg", "1x/dia")], allergies=["Heparina (HIT prévia)"]
    )[0]
    # AAS -> AINE: reatividade cruzada = atenção; penicilina -> cefalosporina: só info (não vira alerta)
    assert ("alergia", "atencao") in got(
        [ev(0, "Ibuprofeno", 600, "mg", "8/8h")], allergies=["AAS (broncoespasmo)"]
    )[0]
    s, _ = got([ev(0, "Ceftriaxona", 2, "g", "1x/dia", route="EV")], allergies=["Penicilina"])
    assert ("alergia", "info") in s and not any(sev != "info" for _, sev in s)
    assert got([ev(0, "Dipirona", 1, "g", "6/6h")], allergies=["Látex"])[0] == set()


def test_duplicidade_terapeutica_por_classe():
    s, _ = got(
        [
            ev(0, "Enoxaparina", 40, "mg", "1x/dia"),
            ev(5, "Heparina não fracionada", 1000, "UI/h", "contínuo", route="EV"),
        ]
    )
    assert ("duplicidade", "critico") in s
    assert ("duplicidade", "atencao") in got(
        [ev(0, "Ibuprofeno", 600, "mg", "8/8h"), ev(2, "Cetorolaco", 30, "mg", "6/6h")]
    )[0]
    # basal + rápida e clopidogrel + AAS não são duplicidade
    assert (
        got(
            [
                ev(0, "Insulina glargina", 14, "UI", "noite"),
                ev(1, "Insulina regular", 4, "UI", "6/6h"),
            ]
        )[0]
        == set()
    )
    assert not any(
        c == "duplicidade"
        for c, _ in got(
            [ev(0, "Clopidogrel", 75, "mg", "1x/dia"), ev(1, "AAS", 100, "mg", "1x/dia")]
        )[0]
    )
    # suspender o anterior antes de iniciar o novo: troca, não duplicidade
    troca = [
        ev(0, "Omeprazol", 40, "mg", "1x/dia"),
        ev(10, "Omeprazol", 40, "mg", "1x/dia", "suspensao"),
        ev(11, "Pantoprazol", 40, "mg", "1x/dia"),
    ]
    assert not any(c == "duplicidade" for c, _ in got(troca)[0])


def test_instabilidade_tres_mudancas_em_24h():
    ordens = [ev(0, "Tramadol", 100, "mg", "8/8h", route="EV")]
    for h, d in ((4, 75), (9, 100), (15, 75)):
        ordens.append(ev(h, "Tramadol", d, "mg", "8/8h", "ajuste", route="EV"))
    assert ("instabilidade", "atencao") in got(ordens)[0]
    assert not any(c == "instabilidade" for c, _ in got(ordens[:3])[0])  # só 2 mudanças


def test_mudanca_atipica_em_relacao_ao_historico_do_paciente():
    # o paciente sempre mudou ~10 %; agora 1,9× em um medicamento comum (abaixo do salto de 2×)
    ordens = [ev(0, "Furosemida", 40, "mg", "12/12h", route="EV")]
    dose, h = 40.0, 0
    for f in (1.1, 0.95, 1.08, 1.05):
        dose, h = dose * f, h + 30
        ordens.append(ev(h, "Furosemida", round(dose, 1), "mg", "12/12h", "ajuste", route="EV"))
    ordens.append(
        ev(h + 40, "Furosemida", round(dose * 1.9, 1), "mg", "12/12h", "ajuste", route="EV")
    )
    s, r = got(ordens)
    assert ("mudanca_atipica", "atencao") in s and not any(c == "salto_dose" for c, _ in s)
    assert max(r.series["surpresa"]) >= 0.58


def test_prescricao_normal_nao_gera_alerta_e_contrato():
    ordens = [
        ev(0, "Dipirona", 1, "g", "6/6h se dor"),
        ev(0, "Enoxaparina", 40, "mg", "1x/dia", route="SC"),
        ev(30, "Dipirona", 0.75, "g", "6/6h se dor", "ajuste"),
    ]
    r = detect_prescription_anomalies(ordens, weight_kg=80)
    assert r.kind == "prescricao" and r.findings == [] and r.risk_level == "baixo"
    assert r.series["t"] and len(r.series["t"]) == len(r.series["drug"]) == 3
    assert detect_prescription_anomalies([]).warnings


def test_resultado_carrega_fonte_e_vigilancia():
    r = detect_prescription_anomalies([ev(0, "Dipirona", 1, "g", "4/4h")])
    assert r.severity == "critico" and r.risk_score > 0.5
    assert r.series["anomaly_index"] == [0] and "dipirona" in r.details["referencias"]
    assert match_drug("Cloreto de potássio 19,1%").key == "cloreto_de_potassio"
    assert match_drug("Soro fisiológico 0,9%") is None
