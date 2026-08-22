"""Geração determinística de pacientes/prontuários sintéticos (fictícios).

Por que sintético? O desafio exige "dataset anonimizado ou exemplo de dados sintéticos".
Aqui geramos, com ``Faker`` (pt_BR) e semente fixa, um hospital fictício coerente com
os protocolos da base de conhecimento — incluindo **PII fictícia propositalmente
inserida nas evoluções** (CPF, telefone, endereço, nome da mãe) para demonstrar o
anonimizador em ação antes de qualquer dado chegar à LLM.

Alguns pacientes são "cenários dirigidos" (sepse com lactato atrasado, CAD, SCA,
hipercalemia em LRA, AVC em janela…) para que os fluxos LangGraph tenham o que
encontrar; os demais são internações estáveis variadas.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from faker import Faker

SEED = 2026
DEFAULT_NOW = datetime(2026, 8, 21, 8, 0, 0)  # "agora" fixo para reprodutibilidade (testes)
NOW = DEFAULT_NOW  # ajustado em generate_patients(now=...) para que prazos fiquem relativos ao seed


@dataclass
class Scenario:
    key: str
    sex: str
    age: int
    ward: str
    primary_diagnosis: str
    comorbidities: list[str]
    allergies: list[str]
    vitals: list[dict[str, Any]]  # mais recente por último
    exams: list[dict[str, Any]]
    medications: list[dict[str, Any]]
    notes: list[dict[str, Any]]
    admission_days_ago: float = 1.0
    extra: dict[str, Any] = field(default_factory=dict)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _ago(hours: float) -> str:
    return _iso(NOW - timedelta(hours=hours))


def _exam(
    name: str,
    category: str,
    status: str,
    *,
    requested_h: float,
    due_h: float | None = None,
    result_h: float | None = None,
    value: str | None = None,
    unit: str | None = None,
    ref: str | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    due = None
    if due_h is not None:
        due = (
            _iso(NOW - timedelta(hours=due_h))
            if due_h >= 0
            else _iso(NOW + timedelta(hours=-due_h))
        )
    return {
        "name": name,
        "category": category,
        "status": status,
        "requested_at": _ago(requested_h),
        "due_at": due,
        "result_at": _ago(result_h) if result_h is not None else None,
        "result_value": value,
        "unit": unit,
        "reference_range": ref,
        "note": note,
    }


def _vital(
    hours_ago: float,
    hr: int,
    sbp: int,
    dbp: int,
    rr: int,
    temp: float,
    spo2: int,
    gcs: int | None = 15,
) -> dict[str, Any]:
    return {
        "measured_at": _ago(hours_ago),
        "hr": hr,
        "sbp": sbp,
        "dbp": dbp,
        "rr": rr,
        "temp_c": temp,
        "spo2": spo2,
        "gcs": gcs,
    }


def _med(
    name: str, dose: str, route: str, freq: str, started_h: float, status: str = "ativo"
) -> dict[str, Any]:
    return {
        "name": name,
        "dose": dose,
        "route": route,
        "frequency": freq,
        "started_at": _ago(started_h),
        "status": status,
    }


def _note(hours_ago: float, author: str, ntype: str, text: str) -> dict[str, Any]:
    return {"created_at": _ago(hours_ago), "author": author, "type": ntype, "text": text}


# ---------------------------------------------------------------------------
# Cenários dirigidos — casam com os protocolos PROT-001..016
# ---------------------------------------------------------------------------
def _scenarios() -> list[Scenario]:
    s: list[Scenario] = []
    s.append(
        Scenario(
            key="sepse_pac",
            sex="M",
            age=67,
            ward="Pronto-Socorro",
            primary_diagnosis="Pneumonia adquirida na comunidade com suspeita de sepse",
            comorbidities=["Hipertensão arterial", "DPOC", "Tabagismo (40 maços-ano)"],
            allergies=["Penicilina (urticária)"],
            vitals=[
                _vital(6, 98, 118, 72, 20, 38.2, 94),
                _vital(3, 108, 102, 60, 24, 38.8, 92),
                _vital(0.5, 116, 88, 54, 27, 39.1, 90, 14),
            ],
            exams=[
                _exam(
                    "Lactato arterial",
                    "laboratorio",
                    "concluido",
                    requested_h=5,
                    result_h=4.2,
                    value="3,4",
                    unit="mmol/L",
                    ref="0,5–2,0",
                ),
                _exam(
                    "Lactato arterial (reavaliação 2h)",
                    "laboratorio",
                    "atrasado",
                    requested_h=4,
                    due_h=1.5,
                    note="Solicitado pelo protocolo de sepse; não coletado",
                ),
                _exam(
                    "Hemoculturas (2 amostras)", "laboratorio", "coletado", requested_h=5, due_h=-48
                ),
                _exam(
                    "Hemograma completo",
                    "laboratorio",
                    "concluido",
                    requested_h=5,
                    result_h=3.5,
                    value="Leucócitos 19.800 (bastões 12%)",
                    unit="/mm³",
                    ref="4.000–10.000",
                ),
                _exam(
                    "Leucócitos",
                    "laboratorio",
                    "concluido",
                    requested_h=5,
                    result_h=3.5,
                    value="19800",
                    unit="/mm³",
                    ref="4000–10000",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=5,
                    result_h=3.5,
                    value="1,9",
                    unit="mg/dL",
                    ref="0,7–1,2",
                ),
                _exam(
                    "PCR",
                    "laboratorio",
                    "concluido",
                    requested_h=5,
                    result_h=3.5,
                    value="212",
                    unit="mg/L",
                    ref="< 5",
                ),
                _exam(
                    "Radiografia de tórax",
                    "imagem",
                    "concluido",
                    requested_h=5,
                    result_h=4,
                    value="Consolidação em lobo inferior direito",
                    note="Laudo preliminar",
                ),
                _exam("Gasometria arterial", "laboratorio", "pendente", requested_h=0.8, due_h=-1),
            ],
            medications=[
                _med("Ceftriaxona", "2 g", "EV", "1x/dia", 3.5),
                _med("Azitromicina", "500 mg", "EV", "1x/dia", 3.5),
                _med("Ringer lactato", "1.000 mL", "EV", "bolus", 3),
                _med("Dipirona", "1 g", "EV", "6/6h se dor/febre", 5),
            ],
            notes=[
                _note(
                    5.5,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, CPF {CPF}, telefone {PHONE}, residente à {ADDR}. Mãe: {MOTHER}. "
                    "Admitido com tosse produtiva há 4 dias, febre e dispneia progressiva. Ao exame: REG, taquipneico, crepitações em base D. "
                    "HD: PAC. Iniciado protocolo de sepse (qSOFA 2). Solicitados lactato, hemoculturas, HMG, função renal, RX tórax. Antibiótico em 45 min da triagem.",
                ),
                _note(
                    2.5,
                    "Enf. Carla Mendes",
                    "evolucao",
                    "Paciente {NAME} mantém febre 38,8 °C, PA 102/60, FR 24. Acompanhante (esposa, Sra. {SPOUSE}, tel {PHONE2}) orientada. Aguardando reavaliação de lactato.",
                ),
                _note(
                    0.7,
                    "Dr. Marcos Vinícius Lima",
                    "evolucao",
                    "Piora hemodinâmica: PA 88/54 após 1.000 mL de cristaloide, FR 27, sonolento (GCS 14). Lactato de controle ainda não coletado. Considerar reavaliação imediata conforme protocolo.",
                ),
            ],
            admission_days_ago=0.25,
        )
    )
    s.append(
        Scenario(
            key="cad",
            sex="F",
            age=24,
            ward="Pronto-Socorro",
            primary_diagnosis="Cetoacidose diabética (DM1)",
            comorbidities=["Diabetes mellitus tipo 1"],
            allergies=[],
            vitals=[_vital(2, 118, 98, 60, 26, 37.1, 97), _vital(0.3, 112, 104, 64, 24, 37.0, 98)],
            exams=[
                _exam(
                    "Glicemia capilar",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.9,
                    value="486",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Gasometria arterial",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.5,
                    value="pH 7,14 / HCO3 9",
                    unit="",
                    ref="pH 7,35–7,45",
                ),
                _exam(
                    "pH arterial",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.5,
                    value="7,14",
                    unit="",
                    ref="7,35–7,45",
                ),
                _exam(
                    "Bicarbonato",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.5,
                    value="9",
                    unit="mmol/L",
                    ref="22–26",
                ),
                _exam(
                    "Potássio",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.5,
                    value="3,1",
                    unit="mmol/L",
                    ref="3,5–5,0",
                ),
                _exam(
                    "Cetonemia",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.5,
                    value="5,8",
                    unit="mmol/L",
                    ref="< 0,6",
                ),
                _exam(
                    "Potássio (controle 2h)", "laboratorio", "pendente", requested_h=0.5, due_h=-1.5
                ),
                _exam(
                    "Glicemia capilar horária",
                    "laboratorio",
                    "pendente",
                    requested_h=0.2,
                    due_h=-0.8,
                ),
            ],
            medications=[
                _med("Soro fisiológico 0,9%", "1.000 mL/h", "EV", "contínuo", 1.8),
                _med("Insulina regular", "0,1 UI/kg/h", "EV", "bomba de infusão", 1.2),
                _med("Cloreto de potássio 19,1%", "20 mEq/L", "EV", "em cada litro de SF", 1.0),
            ],
            notes=[
                _note(
                    2,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, DM1 há 10 anos, abandono de insulina há 3 dias. Poliúria, polidipsia, vômitos, hálito cetônico. Glicemia 486, pH 7,14, HCO3 9, K 3,1. Iniciado protocolo de CAD: hidratação, reposição de K antes da insulina (K < 3,3), depois insulina EV. CPF {CPF}. Contato: {PHONE}.",
                )
            ],
            admission_days_ago=0.1,
        )
    )
    s.append(
        Scenario(
            key="sca",
            sex="M",
            age=58,
            ward="Unidade Coronariana",
            primary_diagnosis="Síndrome coronariana aguda sem supra de ST (em investigação)",
            comorbidities=["Diabetes mellitus tipo 2", "Dislipidemia", "Hipertensão arterial"],
            allergies=["AAS (broncoespasmo)"],
            vitals=[_vital(4, 92, 150, 94, 18, 36.6, 97), _vital(1, 84, 138, 86, 16, 36.5, 98)],
            exams=[
                _exam(
                    "ECG 12 derivações",
                    "cardiologia",
                    "concluido",
                    requested_h=4,
                    result_h=3.9,
                    value="Infradesnivelamento de ST 1,5 mm em V4-V6",
                    note="Sem supra de ST",
                ),
                _exam(
                    "Troponina ultrassensível (0h)",
                    "laboratorio",
                    "concluido",
                    requested_h=4,
                    result_h=3,
                    value="68",
                    unit="ng/L",
                    ref="< 14 (p99)",
                ),
                _exam(
                    "Troponina ultrassensível (3h)",
                    "laboratorio",
                    "atrasado",
                    requested_h=1,
                    due_h=0.5,
                    note="Curva de troponina pendente",
                ),
                _exam(
                    "Ecocardiograma transtorácico",
                    "cardiologia",
                    "pendente",
                    requested_h=2,
                    due_h=-12,
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=4,
                    result_h=3,
                    value="1,1",
                    unit="mg/dL",
                    ref="0,7–1,2",
                ),
                _exam(
                    "Hemoglobina",
                    "laboratorio",
                    "concluido",
                    requested_h=4,
                    result_h=3,
                    value="13,8",
                    unit="g/dL",
                    ref="13–17",
                ),
            ],
            medications=[
                _med("Clopidogrel", "300 mg ataque, 75 mg/dia", "VO", "1x/dia", 3.5),
                _med("Enoxaparina", "1 mg/kg", "SC", "12/12h", 3.5),
                _med("Atorvastatina", "80 mg", "VO", "1x/dia (noite)", 3.5),
                _med("Metoprolol", "25 mg", "VO", "12/12h", 3),
            ],
            notes=[
                _note(
                    4,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, dor torácica opressiva há 2h irradiada para MSE, sudorese. ECG com infra de ST V4-V6. Troponina 0h 68 ng/L. HEART score 6. Alergia a AAS — usar clopidogrel. Aguardando troponina 3h (ATRASADA) e eco. CPF {CPF}, telefone {PHONE}.",
                )
            ],
            admission_days_ago=0.2,
        )
    )
    s.append(
        Scenario(
            key="avc",
            sex="F",
            age=72,
            ward="Pronto-Socorro",
            primary_diagnosis="AVC isquêmico agudo em janela terapêutica",
            comorbidities=["Fibrilação atrial (sem anticoagulação)", "Hipertensão arterial"],
            allergies=[],
            vitals=[
                _vital(1.2, 96, 178, 98, 18, 36.7, 96, 14),
                _vital(0.2, 92, 172, 96, 18, 36.7, 96, 14),
            ],
            exams=[
                _exam(
                    "Tomografia de crânio sem contraste",
                    "imagem",
                    "concluido",
                    requested_h=1.1,
                    result_h=0.7,
                    value="Sem sinais de hemorragia; ASPECTS 9",
                    note="Porta-TC 22 min",
                ),
                _exam(
                    "Glicemia capilar",
                    "laboratorio",
                    "concluido",
                    requested_h=1.2,
                    result_h=1.15,
                    value="132",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Plaquetas",
                    "laboratorio",
                    "concluido",
                    requested_h=1.1,
                    result_h=0.6,
                    value="245",
                    unit="mil/mm³",
                    ref="150–450",
                ),
                _exam(
                    "INR",
                    "laboratorio",
                    "concluido",
                    requested_h=1.1,
                    result_h=0.6,
                    value="1,0",
                    unit="",
                    ref="0,8–1,2",
                ),
                _exam(
                    "Angiotomografia de vasos cervicais e intracranianos",
                    "imagem",
                    "pendente",
                    requested_h=0.6,
                    due_h=-0.3,
                ),
            ],
            medications=[],
            notes=[
                _note(
                    1.2,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, trazida pelo SAMU com hemiparesia direita e afasia, início dos sintomas há 80 min (testemunhado pela filha, Sra. {SPOUSE}, tel {PHONE}). NIHSS 14. Glicemia 132. TC sem sangramento. PA 178/98 — acima do alvo para trombólise (≤ 185/110 ok). Discutir trombólise/trombectomia com neurologia. Acompanhante informa CPF {CPF}.",
                )
            ],
            admission_days_ago=0.06,
        )
    )
    s.append(
        Scenario(
            key="hipercalemia_lra",
            sex="M",
            age=79,
            ward="Clínica Médica",
            primary_diagnosis="Lesão renal aguda com hipercalemia",
            comorbidities=[
                "Doença renal crônica estágio 3b",
                "Insuficiência cardíaca (FE 35%)",
                "Diabetes mellitus tipo 2",
            ],
            allergies=["Contraste iodado"],
            vitals=[_vital(8, 58, 128, 76, 18, 36.4, 95), _vital(1, 52, 118, 70, 18, 36.3, 95)],
            exams=[
                _exam(
                    "Potássio",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=1.5,
                    value="6,4",
                    unit="mmol/L",
                    ref="3,5–5,0",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=1.5,
                    value="3,6",
                    unit="mg/dL",
                    ref="0,7–1,2",
                    note="Basal 1,8",
                ),
                _exam(
                    "Ureia",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=1.5,
                    value="138",
                    unit="mg/dL",
                    ref="15–45",
                ),
                _exam(
                    "ECG 12 derivações",
                    "cardiologia",
                    "atrasado",
                    requested_h=1.4,
                    due_h=0.9,
                    note="Solicitado por K 6,4 — ainda não realizado",
                ),
                _exam("Gasometria venosa", "laboratorio", "pendente", requested_h=1.2, due_h=-0.5),
            ],
            medications=[
                _med("Espironolactona", "25 mg", "VO", "1x/dia", 72, status="suspenso"),
                _med("Enalapril", "10 mg", "VO", "12/12h", 72, status="suspenso"),
                _med("Furosemida", "40 mg", "EV", "12/12h", 20),
                _med("Insulina NPH", "12 UI", "SC", "manhã", 72),
            ],
            notes=[
                _note(
                    20,
                    "Dra. Ana Beatriz Souza",
                    "evolucao",
                    "Paciente: {NAME}, {AGE} anos, internado por descompensação de IC. Evolui com oligúria (débito 15 mL/h) e piora de função renal. Suspensos IECA e espironolactona. CPF {CPF}.",
                ),
                _note(
                    1.2,
                    "Dra. Ana Beatriz Souza",
                    "evolucao",
                    "K 6,4 mmol/L e creatinina 3,6. ECG solicitado com urgência, ainda não realizado. Bradicardia 52 bpm. Avaliar medidas para hipercalemia e parecer da nefrologia.",
                ),
            ],
            admission_days_ago=3,
        )
    )
    s.append(
        Scenario(
            key="icc",
            sex="F",
            age=81,
            ward="Cardiologia",
            primary_diagnosis="Insuficiência cardíaca descompensada (perfil B: quente e úmido)",
            comorbidities=[
                "IC com FE reduzida (30%)",
                "Fibrilação atrial (anticoagulada)",
                "DRC estágio 3a",
            ],
            allergies=[],
            vitals=[_vital(12, 102, 134, 82, 24, 36.5, 91), _vital(2, 96, 128, 80, 22, 36.5, 93)],
            exams=[
                _exam(
                    "BNP",
                    "laboratorio",
                    "concluido",
                    requested_h=14,
                    result_h=12,
                    value="1.840",
                    unit="pg/mL",
                    ref="< 100",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=14,
                    result_h=12,
                    value="1,6",
                    unit="mg/dL",
                    ref="0,6–1,1",
                ),
                _exam(
                    "Potássio",
                    "laboratorio",
                    "concluido",
                    requested_h=14,
                    result_h=12,
                    value="4,2",
                    unit="mmol/L",
                    ref="3,5–5,0",
                ),
                _exam(
                    "Radiografia de tórax",
                    "imagem",
                    "concluido",
                    requested_h=14,
                    result_h=13,
                    value="Congestão hilar bilateral, derrame pleural D pequeno",
                ),
                _exam("Ecocardiograma", "cardiologia", "pendente", requested_h=10, due_h=-20),
                _exam("Eletrólitos (controle)", "laboratorio", "pendente", requested_h=2, due_h=-4),
            ],
            medications=[
                _med("Furosemida", "40 mg", "EV", "8/8h", 12),
                _med("Apixabana", "2,5 mg", "VO", "12/12h", 96),
                _med("Carvedilol", "6,25 mg", "VO", "12/12h", 96),
                _med("Sacubitril/valsartana", "24/26 mg", "VO", "12/12h", 96),
            ],
            notes=[
                _note(
                    14,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, dispneia progressiva, ortopneia, edema MMII 3+/4+. Ganho de 4 kg em 1 semana. BNP 1.840. Iniciado diurético EV. Monitorar diurese, eletrólitos e função renal. Telefone {PHONE}.",
                )
            ],
            admission_days_ago=0.6,
        )
    )
    s.append(
        Scenario(
            key="hipoglicemia",
            sex="M",
            age=70,
            ward="Clínica Médica",
            primary_diagnosis="Hipoglicemia em paciente com DM2 em uso de sulfonilureia",
            comorbidities=["Diabetes mellitus tipo 2", "DRC estágio 3", "Hipertensão arterial"],
            allergies=[],
            vitals=[
                _vital(3, 88, 140, 84, 16, 36.4, 97, 13),
                _vital(0.5, 80, 136, 82, 16, 36.5, 97, 15),
            ],
            exams=[
                _exam(
                    "Glicemia capilar",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=2.95,
                    value="42",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Glicemia capilar (15 min)",
                    "laboratorio",
                    "concluido",
                    requested_h=2.7,
                    result_h=2.65,
                    value="78",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Glicemia capilar (1 h)",
                    "laboratorio",
                    "concluido",
                    requested_h=2,
                    result_h=1.9,
                    value="96",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=1.5,
                    value="2,1",
                    unit="mg/dL",
                    ref="0,7–1,2",
                ),
                _exam(
                    "Glicemia capilar (controle 4/4h)",
                    "laboratorio",
                    "pendente",
                    requested_h=0.5,
                    due_h=-3,
                ),
            ],
            medications=[
                _med("Glibenclamida", "5 mg", "VO", "12/12h", 120, status="suspenso"),
                _med("Glicose 50%", "40 mL", "EV", "bolus (feito)", 2.9),
                _med("Soro glicosado 10%", "60 mL/h", "EV", "contínuo", 2.5),
            ],
            notes=[
                _note(
                    3,
                    "Enf. Carla Mendes",
                    "evolucao",
                    "Paciente: {NAME} encontrado sonolento, sudoreico, glicemia capilar 42 mg/dL. Administrada glicose 50% conforme protocolo, médico acionado. Recuperou consciência em 10 min.",
                ),
                _note(
                    2.5,
                    "Dra. Ana Beatriz Souza",
                    "evolucao",
                    "Hipoglicemia por sulfonilureia em DRC (meia-vida prolongada). Suspensa glibenclamida; manter SG10% e glicemias 4/4h por 24-48h pelo risco de recorrência.",
                ),
            ],
            admission_days_ago=5,
        )
    )
    s.append(
        Scenario(
            key="asma",
            sex="F",
            age=31,
            ward="Pronto-Socorro",
            primary_diagnosis="Exacerbação grave de asma",
            comorbidities=["Asma persistente moderada", "Rinite alérgica"],
            allergies=["Dipirona (angioedema)"],
            vitals=[
                _vital(1.5, 124, 128, 80, 30, 36.8, 90),
                _vital(0.3, 110, 124, 78, 24, 36.8, 94),
            ],
            exams=[
                _exam(
                    "Peak flow",
                    "outros",
                    "concluido",
                    requested_h=1.5,
                    result_h=1.45,
                    value="38% do previsto",
                    note="Pré-broncodilatador",
                ),
                _exam(
                    "Gasometria arterial",
                    "laboratorio",
                    "concluido",
                    requested_h=1.2,
                    result_h=0.8,
                    value="pH 7,38 / PaCO2 41 / PaO2 62",
                    unit="",
                    ref="",
                ),
                _exam(
                    "PaCO2",
                    "laboratorio",
                    "concluido",
                    requested_h=1.2,
                    result_h=0.8,
                    value="41",
                    unit="mmHg",
                    ref="35–45",
                    note="Normocapnia em crise grave = sinal de alerta (fadiga)",
                ),
                _exam("Radiografia de tórax", "imagem", "pendente", requested_h=0.5, due_h=-1),
                _exam("Peak flow (controle 1h)", "outros", "pendente", requested_h=0.4, due_h=-0.6),
            ],
            medications=[
                _med("Salbutamol spray + espaçador", "4 jatos", "INAL", "a cada 20 min (3x)", 1.4),
                _med("Ipratrópio", "4 jatos", "INAL", "a cada 20 min (3x)", 1.4),
                _med("Prednisona", "50 mg", "VO", "dose única", 1.2),
                _med("Oxigênio", "2 L/min", "CN", "alvo SpO2 93-95%", 1.4),
            ],
            notes=[
                _note(
                    1.5,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, crise asmática há 6h sem resposta ao salbutamol domiciliar. Fala frases curtas, tiragem, sibilos difusos, SpO2 90%. Peak flow 38%. Iniciado protocolo de exacerbação grave. Atenção: PaCO2 41 em crise grave (normocapnia) — risco de fadiga; reavaliar em 1h. Alergia: dipirona. Contato: {PHONE}.",
                )
            ],
            admission_days_ago=0.08,
        )
    )
    s.append(
        Scenario(
            key="delirium",
            sex="M",
            age=84,
            ward="Geriatria",
            primary_diagnosis="Delirium hiperativo pós-operatório (fratura de fêmur)",
            comorbidities=[
                "Demência leve",
                "Hipertensão arterial",
                "Hiperplasia prostática benigna",
            ],
            allergies=[],
            vitals=[
                _vital(10, 92, 146, 84, 18, 37.4, 95, 14),
                _vital(1, 98, 150, 86, 20, 37.8, 94, 13),
            ],
            exams=[
                _exam(
                    "Hemograma",
                    "laboratorio",
                    "concluido",
                    requested_h=10,
                    result_h=8,
                    value="Hb 10,1 / Leuco 12.300",
                    unit="",
                    ref="",
                ),
                _exam(
                    "Hemoglobina",
                    "laboratorio",
                    "concluido",
                    requested_h=10,
                    result_h=8,
                    value="10,1",
                    unit="g/dL",
                    ref="13–17",
                ),
                _exam(
                    "Sódio",
                    "laboratorio",
                    "concluido",
                    requested_h=10,
                    result_h=8,
                    value="131",
                    unit="mmol/L",
                    ref="135–145",
                ),
                _exam(
                    "Urina tipo 1 + urocultura", "laboratorio", "pendente", requested_h=6, due_h=-18
                ),
                _exam(
                    "Glicemia capilar",
                    "laboratorio",
                    "concluido",
                    requested_h=1,
                    result_h=0.9,
                    value="118",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "Radiografia de tórax",
                    "imagem",
                    "atrasado",
                    requested_h=8,
                    due_h=2,
                    note="Solicitada para investigar febre; não realizada",
                ),
            ],
            medications=[
                _med("Enoxaparina", "40 mg", "SC", "1x/dia", 48),
                _med("Dipirona", "1 g", "EV", "6/6h", 48),
                _med("Morfina", "2 mg", "EV", "se dor intensa", 48),
                _med("Tansulosina", "0,4 mg", "VO", "1x/dia", 48),
            ],
            notes=[
                _note(
                    48,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, POI de osteossíntese de fêmur D. Residente à {ADDR}. Filha {SPOUSE} ({PHONE}) como contato.",
                ),
                _note(
                    1.5,
                    "Enf. Carla Mendes",
                    "evolucao",
                    "Paciente {NAME} agitado, desorientado, tentando retirar acesso venoso. CAM-ICU positivo. Febrícula 37,8 °C. Sonda vesical de demora desde cirurgia (48h). Médico comunicado — investigar causas (infecção, dor, retenção, medicações).",
                ),
            ],
            admission_days_ago=2,
        )
    )
    s.append(
        Scenario(
            key="anafilaxia",
            sex="F",
            age=45,
            ward="Pronto-Socorro",
            primary_diagnosis="Anafilaxia após contraste iodado (resolvida, em observação)",
            comorbidities=["Asma leve"],
            allergies=["Contraste iodado (anafilaxia — 21/08/2026)"],
            vitals=[
                _vital(3, 128, 78, 44, 28, 36.6, 89),
                _vital(2, 104, 104, 66, 20, 36.6, 96),
                _vital(0.5, 88, 118, 74, 16, 36.6, 98),
            ],
            exams=[
                _exam("Triptase sérica", "laboratorio", "coletado", requested_h=2.5, due_h=-24),
                _exam(
                    "ECG",
                    "cardiologia",
                    "concluido",
                    requested_h=2.8,
                    result_h=2.7,
                    value="Taquicardia sinusal",
                ),
            ],
            medications=[
                _med("Adrenalina IM", "0,5 mg", "IM", "dose única (vasto lateral)", 2.9),
                _med("Soro fisiológico 0,9%", "1.000 mL", "EV", "bolus", 2.8),
                _med("Hidrocortisona", "200 mg", "EV", "dose única", 2.7),
                _med("Difenidramina", "50 mg", "EV", "dose única", 2.7),
            ],
            notes=[
                _note(
                    3,
                    "Dr. Marcos Vinícius Lima",
                    "evolucao",
                    "Paciente: {NAME}, {AGE} anos, durante TC contrastada apresentou urticária difusa, angioedema labial, broncoespasmo e hipotensão 78/44. Adrenalina IM 0,5 mg imediata, decúbito, O2, cristaloide. Melhora em 15 min. Observação mínima de 6-8h pelo risco de reação bifásica. Prescrever adrenalina autoinjetável na alta e registrar alergia. CPF {CPF}.",
                )
            ],
            admission_days_ago=0.15,
        )
    )
    s.append(
        Scenario(
            key="crise_hipertensiva",
            sex="M",
            age=55,
            ward="Pronto-Socorro",
            primary_diagnosis="Emergência hipertensiva com encefalopatia",
            comorbidities=["Hipertensão arterial (má adesão)", "Tabagismo"],
            allergies=[],
            vitals=[
                _vital(2, 94, 226, 134, 18, 36.7, 97, 14),
                _vital(0.4, 90, 204, 120, 18, 36.7, 97, 15),
            ],
            exams=[
                _exam(
                    "Tomografia de crânio",
                    "imagem",
                    "concluido",
                    requested_h=1.8,
                    result_h=1.2,
                    value="Sem hemorragia ou isquemia aguda",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=1.8,
                    result_h=1,
                    value="1,4",
                    unit="mg/dL",
                    ref="0,7–1,2",
                ),
                _exam(
                    "Troponina",
                    "laboratorio",
                    "concluido",
                    requested_h=1.8,
                    result_h=1,
                    value="9",
                    unit="ng/L",
                    ref="< 14",
                ),
                _exam("Fundoscopia", "outros", "pendente", requested_h=1.5, due_h=-2),
                _exam("Urina tipo 1", "laboratorio", "pendente", requested_h=1.5, due_h=-2),
            ],
            medications=[
                _med(
                    "Nitroprussiato de sódio",
                    "0,5 mcg/kg/min (titulando)",
                    "EV",
                    "bomba de infusão",
                    1.5,
                )
            ],
            notes=[
                _note(
                    2,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, cefaleia intensa, confusão mental, PA 226/134. TC sem sangramento. HD: emergência hipertensiva (encefalopatia). Alvo: reduzir PAM ≤ 25% na 1ª hora. Leito de UTI solicitado. Telefone {PHONE}.",
                )
            ],
            admission_days_ago=0.1,
        )
    )
    s.append(
        Scenario(
            key="itu_complicada",
            sex="F",
            age=63,
            ward="Clínica Médica",
            primary_diagnosis="Pielonefrite aguda (ITU complicada)",
            comorbidities=["Diabetes mellitus tipo 2", "Litíase renal"],
            allergies=["Sulfa (rash)"],
            vitals=[_vital(20, 104, 112, 70, 20, 38.9, 96), _vital(1, 88, 120, 76, 18, 37.6, 97)],
            exams=[
                _exam(
                    "Urocultura",
                    "laboratorio",
                    "coletado",
                    requested_h=22,
                    due_h=-26,
                    note="Coletada antes do antibiótico",
                ),
                _exam("Hemoculturas", "laboratorio", "coletado", requested_h=22, due_h=-26),
                _exam(
                    "Urina tipo 1",
                    "laboratorio",
                    "concluido",
                    requested_h=22,
                    result_h=20,
                    value="Leucocitúria > 100/campo, nitrito +, bacteriúria",
                ),
                _exam(
                    "Creatinina",
                    "laboratorio",
                    "concluido",
                    requested_h=22,
                    result_h=20,
                    value="1,3",
                    unit="mg/dL",
                    ref="0,6–1,1",
                ),
                _exam(
                    "Ultrassom de rins e vias urinárias",
                    "imagem",
                    "pendente",
                    requested_h=18,
                    due_h=-6,
                ),
            ],
            medications=[
                _med("Ceftriaxona", "1 g", "EV", "1x/dia", 21),
                _med("Dipirona", "1 g", "VO", "6/6h se febre", 21),
            ],
            notes=[
                _note(
                    22,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, febre, calafrios, dor lombar D, Giordano +. Diabética. ITU complicada — iniciado ceftriaxona conforme protocolo, após coleta de culturas. US solicitado para afastar obstrução (litíase). Alergia a sulfa. CPF {CPF}.",
                )
            ],
            admission_days_ago=1,
        )
    )
    # Estáveis / variados
    s.append(
        Scenario(
            key="pos_op_estavel",
            sex="M",
            age=42,
            ward="Cirurgia Geral",
            primary_diagnosis="Pós-operatório de colecistectomia videolaparoscópica (POI 1)",
            comorbidities=["Obesidade grau I"],
            allergies=[],
            vitals=[_vital(12, 84, 126, 78, 16, 36.8, 98), _vital(2, 78, 122, 76, 16, 36.6, 98)],
            exams=[
                _exam(
                    "Hemograma",
                    "laboratorio",
                    "concluido",
                    requested_h=12,
                    result_h=10,
                    value="Hb 14,2 / Leuco 9.800",
                ),
                _exam(
                    "Hemoglobina",
                    "laboratorio",
                    "concluido",
                    requested_h=12,
                    result_h=10,
                    value="14,2",
                    unit="g/dL",
                    ref="13–17",
                ),
            ],
            medications=[
                _med("Dipirona", "1 g", "VO", "6/6h", 20),
                _med("Enoxaparina", "40 mg", "SC", "1x/dia", 20),
                _med("Ondansetrona", "4 mg", "EV", "8/8h se náusea", 20),
            ],
            notes=[
                _note(
                    20,
                    "Dr. Marcos Vinícius Lima",
                    "evolucao",
                    "Paciente: {NAME}, POI colecistectomia VL sem intercorrências. Dor controlada (EVA 2). Deambulando. Previsão de alta amanhã. CPF {CPF}.",
                )
            ],
            admission_days_ago=1,
        )
    )
    s.append(
        Scenario(
            key="dpoc",
            sex="M",
            age=69,
            ward="Pneumologia",
            primary_diagnosis="Exacerbação de DPOC",
            comorbidities=["DPOC GOLD 3", "Cor pulmonale", "Tabagismo ativo"],
            allergies=[],
            vitals=[_vital(24, 98, 132, 80, 24, 37.2, 88), _vital(2, 90, 128, 78, 20, 36.9, 91)],
            exams=[
                _exam(
                    "Gasometria arterial",
                    "laboratorio",
                    "concluido",
                    requested_h=24,
                    result_h=23,
                    value="pH 7,33 / PaCO2 58 / PaO2 56",
                ),
                _exam(
                    "PaCO2",
                    "laboratorio",
                    "concluido",
                    requested_h=24,
                    result_h=23,
                    value="58",
                    unit="mmHg",
                    ref="35–45",
                ),
                _exam(
                    "Radiografia de tórax",
                    "imagem",
                    "concluido",
                    requested_h=24,
                    result_h=22,
                    value="Hiperinsuflação, sem consolidação",
                ),
                _exam(
                    "Gasometria arterial (controle)",
                    "laboratorio",
                    "pendente",
                    requested_h=2,
                    due_h=-2,
                ),
            ],
            medications=[
                _med("Salbutamol + ipratrópio", "nebulização", "INAL", "4/4h", 23),
                _med("Prednisona", "40 mg", "VO", "1x/dia (5 dias)", 23),
                _med("Amoxicilina-clavulanato", "875/125 mg", "VO", "12/12h", 23),
                _med("Oxigênio", "1 L/min", "CN", "alvo SpO2 88-92%", 23),
            ],
            notes=[
                _note(
                    24,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, piora de dispneia e escarro purulento. Gasometria com hipercapnia crônica agudizada leve. Alvo de SpO2 88-92% (retentor de CO2). Contato: {PHONE}.",
                )
            ],
            admission_days_ago=1,
        )
    )
    s.append(
        Scenario(
            key="tev_risco",
            sex="F",
            age=76,
            ward="Ortopedia",
            primary_diagnosis="Fratura de quadril aguardando cirurgia",
            comorbidities=["Osteoporose", "Hipertensão arterial", "Obesidade"],
            allergies=["Heparina (HIT prévia)"],
            vitals=[_vital(10, 86, 138, 82, 16, 36.7, 96), _vital(1, 84, 134, 80, 16, 36.7, 96)],
            exams=[
                _exam(
                    "Hemoglobina",
                    "laboratorio",
                    "concluido",
                    requested_h=10,
                    result_h=8,
                    value="11,2",
                    unit="g/dL",
                    ref="12–16",
                ),
                _exam(
                    "Plaquetas",
                    "laboratorio",
                    "concluido",
                    requested_h=10,
                    result_h=8,
                    value="198",
                    unit="mil/mm³",
                    ref="150–450",
                ),
                _exam(
                    "Risco cirúrgico (cardiologia)",
                    "cardiologia",
                    "pendente",
                    requested_h=9,
                    due_h=-6,
                ),
            ],
            medications=[
                _med("Fondaparinux", "2,5 mg", "SC", "1x/dia", 9),
                _med("Dipirona", "1 g", "EV", "6/6h", 10),
                _med("Tramadol", "50 mg", "EV", "8/8h se dor", 10),
            ],
            notes=[
                _note(
                    10,
                    "Dr. Marcos Vinícius Lima",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, queda da própria altura, fratura transtrocanteriana. Imobilizada. Alto risco de TEV (Caprini 9). Alergia a heparina (HIT) — profilaxia com fondaparinux conforme protocolo. Endereço: {ADDR}.",
                )
            ],
            admission_days_ago=0.5,
        )
    )
    s.append(
        Scenario(
            key="dor_pos_op",
            sex="M",
            age=35,
            ward="Cirurgia Geral",
            primary_diagnosis="Pós-operatório de apendicectomia aberta (POI 1) com dor mal controlada",
            comorbidities=[],
            allergies=["AINEs (úlcera péptica prévia)"],
            vitals=[_vital(6, 96, 130, 82, 18, 37.0, 98), _vital(1, 100, 134, 84, 18, 37.1, 98)],
            exams=[
                _exam(
                    "Hemograma",
                    "laboratorio",
                    "concluido",
                    requested_h=12,
                    result_h=10,
                    value="Hb 13,5 / Leuco 11.200",
                )
            ],
            medications=[
                _med("Dipirona", "1 g", "EV", "6/6h", 20),
                _med("Tramadol", "100 mg", "EV", "8/8h", 20),
            ],
            notes=[
                _note(
                    1,
                    "Enf. Carla Mendes",
                    "evolucao",
                    "Paciente {NAME} refere dor EVA 8/10 mesmo após tramadol. Médico comunicado para reavaliar analgesia (escada analgésica). Contraindicado AINE por úlcera prévia.",
                )
            ],
            admission_days_ago=1,
        )
    )
    s.append(
        Scenario(
            key="pac_estavel",
            sex="F",
            age=52,
            ward="Clínica Médica",
            primary_diagnosis="Pneumonia adquirida na comunidade (CURB-65 = 1) em melhora",
            comorbidities=["Hipotireoidismo"],
            allergies=[],
            vitals=[_vital(30, 100, 124, 78, 22, 38.4, 94), _vital(2, 82, 120, 76, 16, 36.8, 97)],
            exams=[
                _exam(
                    "Hemograma",
                    "laboratorio",
                    "concluido",
                    requested_h=30,
                    result_h=28,
                    value="Leuco 15.200",
                ),
                _exam(
                    "PCR",
                    "laboratorio",
                    "concluido",
                    requested_h=30,
                    result_h=28,
                    value="98",
                    unit="mg/L",
                    ref="< 5",
                ),
                _exam("PCR (controle 48h)", "laboratorio", "pendente", requested_h=6, due_h=-18),
            ],
            medications=[
                _med("Amoxicilina-clavulanato", "875/125 mg", "VO", "12/12h", 29),
                _med("Azitromicina", "500 mg", "VO", "1x/dia", 29),
            ],
            notes=[
                _note(
                    30,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, PAC CURB-65 1, internada por hipoxemia leve. Melhora clínica em 24h. Previsão de alta em 48h se afebril. CPF {CPF}.",
                )
            ],
            admission_days_ago=1.3,
        )
    )
    s.append(
        Scenario(
            key="controle_glicemico",
            sex="M",
            age=61,
            ward="Clínica Médica",
            primary_diagnosis="Celulite de membro inferior em paciente com DM2 (hiperglicemia hospitalar)",
            comorbidities=["Diabetes mellitus tipo 2", "Obesidade", "Insuficiência venosa crônica"],
            allergies=[],
            vitals=[_vital(12, 90, 138, 86, 18, 37.6, 97), _vital(2, 86, 136, 84, 18, 37.2, 97)],
            exams=[
                _exam(
                    "Glicemia capilar (pré-café)",
                    "laboratorio",
                    "concluido",
                    requested_h=3,
                    result_h=2.9,
                    value="248",
                    unit="mg/dL",
                    ref="70–99",
                ),
                _exam(
                    "HbA1c",
                    "laboratorio",
                    "concluido",
                    requested_h=24,
                    result_h=20,
                    value="9,4",
                    unit="%",
                    ref="< 7",
                ),
                _exam(
                    "Glicemia capilar (pré-almoço)",
                    "laboratorio",
                    "pendente",
                    requested_h=1,
                    due_h=-4,
                ),
            ],
            medications=[
                _med("Cefalexina", "1 g", "VO", "6/6h", 24),
                _med("Insulina glargina", "14 UI", "SC", "noite", 20),
                _med(
                    "Insulina regular (escala de correção)",
                    "conforme glicemia",
                    "SC",
                    "pré-refeições",
                    20,
                ),
            ],
            notes=[
                _note(
                    24,
                    "Dra. Ana Beatriz Souza",
                    "admissao",
                    "Paciente: {NAME}, {AGE} anos, celulite em MIE. Glicemias persistentemente > 180 — iniciado esquema basal-bolus conforme protocolo de controle glicêmico do internado (alvo 140-180). Telefone {PHONE}.",
                )
            ],
            admission_days_ago=1,
        )
    )
    return s


# ---------------------------------------------------------------------------
# Montagem do dataset
# ---------------------------------------------------------------------------
def generate_patients(
    n_extra_stable: int = 6, seed: int = SEED, now: datetime | None = None
) -> list[dict[str, Any]]:
    """Gera a lista de pacientes. ``now`` ancora todos os timestamps (default: DEFAULT_NOW)."""
    global NOW
    NOW = (now or DEFAULT_NOW).replace(microsecond=0)
    fake = Faker("pt_BR")
    Faker.seed(seed)
    rng = random.Random(seed)
    scenarios = _scenarios()

    # pacientes estáveis adicionais, gerados de forma simples
    stable_dx = [
        ("Clínica Médica", "Lombalgia mecânica em investigação", ["Hipertensão arterial"]),
        ("Ortopedia", "Pós-operatório de artroplastia de joelho (POI 2)", ["Osteoartrose"]),
        ("Clínica Médica", "Gastroenterite aguda com desidratação leve", []),
        (
            "Cardiologia",
            "Fibrilação atrial paroxística (controle de ritmo)",
            ["Hipertensão arterial"],
        ),
        ("Cirurgia Geral", "Hérnia inguinal — pré-operatório", ["Tabagismo"]),
        ("Clínica Médica", "Anemia ferropriva em investigação", []),
        ("Pneumologia", "Derrame pleural em investigação", ["DPOC"]),
        ("Geriatria", "Pneumonia aspirativa em resolução", ["Demência", "Disfagia"]),
    ]
    for i in range(min(n_extra_stable, len(stable_dx))):
        ward, dx, com = stable_dx[i]
        sex = rng.choice(["F", "M"])
        age = rng.randint(28, 88)
        scenarios.append(
            Scenario(
                key=f"estavel_{i + 1}",
                sex=sex,
                age=age,
                ward=ward,
                primary_diagnosis=dx,
                comorbidities=com,
                allergies=rng.choice([[], [], ["Dipirona"], ["Látex"]]),
                vitals=[
                    _vital(
                        12,
                        rng.randint(64, 90),
                        rng.randint(110, 138),
                        rng.randint(68, 86),
                        rng.randint(14, 18),
                        round(rng.uniform(36.2, 37.2), 1),
                        rng.randint(95, 99),
                    ),
                    _vital(
                        1,
                        rng.randint(64, 90),
                        rng.randint(110, 138),
                        rng.randint(68, 86),
                        rng.randint(14, 18),
                        round(rng.uniform(36.2, 37.2), 1),
                        rng.randint(95, 99),
                    ),
                ],
                exams=[
                    _exam(
                        "Hemograma",
                        "laboratorio",
                        "concluido",
                        requested_h=20,
                        result_h=18,
                        value="Sem alterações relevantes",
                    ),
                    _exam(
                        "Creatinina",
                        "laboratorio",
                        "concluido",
                        requested_h=20,
                        result_h=18,
                        value=f"{rng.uniform(0.7, 1.1):.1f}".replace(".", ","),
                        unit="mg/dL",
                        ref="0,7–1,2",
                    ),
                ],
                medications=[_med("Dipirona", "1 g", "VO", "6/6h se dor", 20)],
                notes=[
                    _note(
                        20,
                        "Dra. Ana Beatriz Souza",
                        "evolucao",
                        "Paciente: {NAME}, {AGE} anos, estável, sem intercorrências. CPF {CPF}. Tel {PHONE}.",
                    )
                ],
                admission_days_ago=rng.randint(1, 4),
            )
        )

    patients: list[dict[str, Any]] = []
    for idx, sc in enumerate(scenarios, start=1):

        def _clean(n: str) -> str:
            for pref in ("Dr. ", "Dra. ", "Sr. ", "Sra. ", "Srta. "):
                n = n.replace(pref, "")
            return n.strip()

        name = _clean(fake.name_female() if sc.sex == "F" else fake.name_male())
        cpf = fake.cpf()
        phone = fake.cellphone_number()
        phone2 = fake.cellphone_number()
        addr = fake.street_address() + ", " + fake.city() + " - " + fake.estado_sigla()
        mother = _clean(fake.name_female())
        spouse = _clean(fake.name_female() if sc.sex == "M" else fake.name_male())
        birth = NOW - timedelta(days=sc.age * 365 + rng.randint(0, 364))
        admission = NOW - timedelta(days=sc.admission_days_ago)
        fill = {
            "{NAME}": name,
            "{AGE}": str(sc.age),
            "{CPF}": cpf,
            "{PHONE}": phone,
            "{PHONE2}": phone2,
            "{ADDR}": addr,
            "{MOTHER}": mother,
            "{SPOUSE}": spouse,
        }
        notes = []
        for n in sc.notes:
            t = n["text"]
            for k, v in fill.items():
                t = t.replace(k, v)
            notes.append({**n, "text": t})
        patients.append(
            {
                "mrn": f"HU{2026000 + idx:07d}",
                "name": name,
                "sex": sc.sex,
                "birth_date": birth.date().isoformat(),
                "age": sc.age,
                "cpf": cpf,
                "phone": phone,
                "address": addr,
                "mother_name": mother,
                "ward": sc.ward,
                "bed": f"{rng.randint(1, 30):02d}{rng.choice('ABC')}",
                "admission_date": _iso(admission),
                "primary_diagnosis": sc.primary_diagnosis,
                "comorbidities": sc.comorbidities,
                "allergies": sc.allergies,
                "weight_kg": round(rng.uniform(52, 104), 1),
                "height_cm": rng.randint(152, 188),
                "blood_type": rng.choice(["O+", "A+", "B+", "AB+", "O-", "A-"]),
                "scenario": sc.key,
                "vitals": sc.vitals,
                "exams": sc.exams,
                "medications": sc.medications,
                "notes": notes,
            }
        )
    return patients


def write_patients(path: str | Path, **kwargs: Any) -> int:
    data = generate_patients(**kwargs)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(
            {
                "generated_at": _iso(NOW),
                "seed": SEED,
                "disclaimer": "Dados 100% sintéticos/fictícios gerados com Faker para fins acadêmicos (Tech Challenge FIAP).",
                "patients": data,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return len(data)


if __name__ == "__main__":  # pragma: no cover
    import sys

    out = sys.argv[1] if len(sys.argv) > 1 else "data/synthetic/patients.json"
    print(f"{write_patients(out)} pacientes sintéticos gravados em {out}")
