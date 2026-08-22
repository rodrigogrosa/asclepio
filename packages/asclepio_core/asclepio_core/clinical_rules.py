"""Regras clínicas determinísticas usadas pelos fluxos automatizados (LangGraph).

Tudo aqui é **código, não LLM**: escores validados, limiares de valores críticos e
gatilhos de protocolo. A LLM entra depois, para *explicar e sugerir* com base nos
protocolos recuperados — e sempre sujeita a validação humana.

Valores de referência educacionais (adulto). Fontes: qSOFA (Sepsis-3), NEWS2 (RCP/NHS),
limites de pânico usuais de laboratório clínico. Material fictício/didático.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

RiskLevel = str  # "baixo" | "moderado" | "alto" | "critico"


# ---------------------------------------------------------------------------
# Valores críticos de exames laboratoriais ("valores de pânico")
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class LabRule:
    exam_keywords: tuple[str, ...]
    unit: str
    low: float | None = None
    high: float | None = None
    label: str = ""
    protocol_hint: str | None = None

    def matches(self, exam_name: str) -> bool:
        n = exam_name.lower()
        return any(k in n for k in self.exam_keywords)


LAB_RULES: list[LabRule] = [
    LabRule(
        ("potássio", "potassio", "k+", "k sérico"),
        "mmol/L",
        low=2.5,
        high=6.0,
        label="Potássio",
        protocol_hint="PROT-012",
    ),
    LabRule(("sódio", "sodio", "na+"), "mmol/L", low=120, high=160, label="Sódio"),
    LabRule(
        ("glicemia", "glicose"),
        "mg/dL",
        low=50,
        high=400,
        label="Glicemia",
        protocol_hint="PROT-011",
    ),
    LabRule(("lactato",), "mmol/L", high=4.0, label="Lactato", protocol_hint="PROT-001"),
    LabRule(("creatinina",), "mg/dL", high=3.0, label="Creatinina", protocol_hint="PROT-010"),
    LabRule(("troponina",), "ng/L", high=52.0, label="Troponina", protocol_hint="PROT-002"),
    LabRule(("hemoglobina", "hb"), "g/dL", low=7.0, label="Hemoglobina"),
    LabRule(("plaquetas",), "mil/mm³", low=50.0, label="Plaquetas"),
    LabRule(("inr", "rni"), "", high=5.0, label="INR"),
    LabRule(
        ("ph ", "ph arterial", "gasometria ph", "ph"),
        "",
        low=7.20,
        high=7.60,
        label="pH arterial",
        protocol_hint="PROT-004",
    ),
    LabRule(
        ("bicarbonato", "hco3"), "mmol/L", low=15.0, label="Bicarbonato", protocol_hint="PROT-004"
    ),
    LabRule(("pcr", "proteína c reativa"), "mg/L", high=200.0, label="PCR"),
    LabRule(
        ("leucócitos", "leucocitos"),
        "/mm³",
        low=2000,
        high=30000,
        label="Leucócitos",
        protocol_hint="PROT-001",
    ),
    LabRule(("cálcio", "calcio"), "mg/dL", low=6.5, high=13.0, label="Cálcio"),
    LabRule(("magnésio", "magnesio"), "mg/dL", low=1.0, high=4.0, label="Magnésio"),
    LabRule(("ureia",), "mg/dL", high=150.0, label="Ureia", protocol_hint="PROT-010"),
    LabRule(("bilirrubina total",), "mg/dL", high=10.0, label="Bilirrubina"),
    LabRule(("pao2",), "mmHg", low=55.0, label="PaO2"),
    LabRule(("paco2",), "mmHg", high=60.0, label="PaCO2", protocol_hint="PROT-013"),
]

# Limiar de atenção (não crítico) para lactato — gatilho de sepse
LACTATE_ALERT = 2.0


@dataclass
class CriticalFinding:
    exam: str
    value: float
    unit: str
    rule: str
    severity: str  # "critico" | "atencao"
    protocol_hint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "exam": self.exam,
            "value": f"{self.value:g} {self.unit}".strip(),
            "rule": self.rule,
            "severity": self.severity,
            "protocol_hint": self.protocol_hint,
        }


def parse_number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    s = str(value).strip().replace(",", ".")
    num = ""
    for ch in s:
        if ch.isdigit() or ch in ".-":
            num += ch
        elif num:
            break
    try:
        return float(num) if num not in {"", "-", "."} else None
    except ValueError:
        return None


def evaluate_labs(exams: list[dict[str, Any]]) -> list[CriticalFinding]:
    """Avalia exames concluídos contra os limiares críticos.

    Cada exame é um dict com pelo menos ``name`` e ``result_value`` (string ou número).
    """
    findings: list[CriticalFinding] = []
    for ex in exams:
        if ex.get("status") not in (None, "concluido") and ex.get("result_value") in (None, ""):
            continue
        val = parse_number(ex.get("result_value"))
        if val is None:
            continue
        name = str(ex.get("name", ""))
        for rule in LAB_RULES:
            if not rule.matches(name):
                continue
            unit = ex.get("unit") or rule.unit
            if rule.high is not None and val > rule.high:
                findings.append(
                    CriticalFinding(
                        name,
                        val,
                        unit,
                        f"{rule.label} > {rule.high:g} {rule.unit}".strip(),
                        "critico",
                        rule.protocol_hint,
                    )
                )
            elif rule.low is not None and val < rule.low:
                findings.append(
                    CriticalFinding(
                        name,
                        val,
                        unit,
                        f"{rule.label} < {rule.low:g} {rule.unit}".strip(),
                        "critico",
                        rule.protocol_hint,
                    )
                )
            elif "lactato" in rule.exam_keywords and val >= LACTATE_ALERT:
                findings.append(
                    CriticalFinding(
                        name,
                        val,
                        unit,
                        f"Lactato ≥ {LACTATE_ALERT:g} mmol/L (gatilho de sepse)",
                        "atencao",
                        "PROT-001",
                    )
                )
            break
    return findings


# ---------------------------------------------------------------------------
# Escores de sinais vitais
# ---------------------------------------------------------------------------
def qsofa(vital: dict[str, Any]) -> tuple[int, list[str]]:
    """qSOFA (Sepsis-3): PAS ≤ 100, FR ≥ 22, alteração de consciência (GCS < 15). ≥ 2 = alto risco."""
    score, reasons = 0, []
    if (vital.get("sbp") or 999) <= 100:
        score += 1
        reasons.append("PAS ≤ 100 mmHg")
    if (vital.get("rr") or 0) >= 22:
        score += 1
        reasons.append("FR ≥ 22 irpm")
    gcs = vital.get("gcs")
    if gcs is not None and gcs < 15:
        score += 1
        reasons.append(f"Alteração de consciência (GCS {gcs})")
    return score, reasons


def news2(vital: dict[str, Any]) -> tuple[int, list[str]]:
    """NEWS2 simplificado (sem O2 suplementar/escala 2). 0-4 baixo, 5-6 médio, ≥7 alto."""
    score, reasons = 0, []
    rr = vital.get("rr") or 16
    if rr <= 8:
        score += 3
        reasons.append("FR ≤ 8")
    elif rr <= 11:
        score += 1
    elif 21 <= rr <= 24:
        score += 2
        reasons.append("FR 21-24")
    elif rr >= 25:
        score += 3
        reasons.append("FR ≥ 25")

    spo2 = vital.get("spo2") or 98
    if spo2 <= 91:
        score += 3
        reasons.append("SpO2 ≤ 91%")
    elif spo2 <= 93:
        score += 2
        reasons.append("SpO2 92-93%")
    elif spo2 <= 95:
        score += 1

    sbp = vital.get("sbp") or 120
    if sbp <= 90:
        score += 3
        reasons.append("PAS ≤ 90")
    elif sbp <= 100:
        score += 2
        reasons.append("PAS 91-100")
    elif sbp <= 110:
        score += 1
    elif sbp >= 220:
        score += 3
        reasons.append("PAS ≥ 220")

    hr = vital.get("hr") or 80
    if hr <= 40:
        score += 3
        reasons.append("FC ≤ 40")
    elif hr <= 50 or 91 <= hr <= 110:
        score += 1
    elif 111 <= hr <= 130:
        score += 2
        reasons.append("FC 111-130")
    elif hr >= 131:
        score += 3
        reasons.append("FC ≥ 131")

    temp = vital.get("temp_c") or 36.5
    if temp <= 35.0:
        score += 3
        reasons.append("T ≤ 35°C")
    elif temp <= 36.0 or 38.1 <= temp <= 39.0:
        score += 1
    elif temp >= 39.1:
        score += 2
        reasons.append("T ≥ 39,1°C")

    gcs = vital.get("gcs")
    if gcs is not None and gcs < 15:
        score += 3
        reasons.append(f"Consciência alterada (GCS {gcs})")
    return score, reasons


# ---------------------------------------------------------------------------
# Gatilhos de protocolo a partir do diagnóstico/queixa (para guiar o RAG)
# ---------------------------------------------------------------------------
PROTOCOL_TRIGGERS: dict[str, tuple[str, ...]] = {
    "PROT-001": (
        "sepse",
        "séptico",
        "septico",
        "infecção",
        "infeccao",
        "pneumonia",
        "itu",
        "bacteremia",
        "febre",
    ),
    "PROT-002": (
        "dor torácica",
        "dor toracica",
        "infarto",
        "iam",
        "sca",
        "síndrome coronariana",
        "coronariana",
        "angina",
    ),
    "PROT-003": (
        "avc",
        "acidente vascular",
        "déficit neurológico",
        "deficit neurologico",
        "hemiparesia",
        "afasia",
    ),
    "PROT-004": ("cetoacidose", "cad", "diabetes descompensado", "hiperglicemia"),
    "PROT-005": ("pneumonia", "pac", "infecção respiratória", "tosse produtiva"),
    "PROT-006": (
        "imobilização",
        "pós-operatório",
        "pos-operatorio",
        "cirurgia",
        "tev",
        "trombose",
        "tromboembolismo",
        "fratura",
    ),
    "PROT-007": ("anafilaxia", "alergia grave", "urticária", "angioedema"),
    "PROT-008": (
        "crise hipertensiva",
        "emergência hipertensiva",
        "hipertensão",
        "hipertensao",
        "pa elevada",
    ),
    "PROT-009": (
        "insuficiência cardíaca",
        "insuficiencia cardiaca",
        "icc",
        "ic descompensada",
        "congestão",
        "edema agudo",
    ),
    "PROT-010": (
        "lesão renal",
        "lesao renal",
        "lra",
        "insuficiência renal",
        "creatinina",
        "oligúria",
    ),
    "PROT-011": ("hipoglicemia", "glicemia", "insulina", "diabetes"),
    "PROT-012": ("hipercalemia", "potássio", "potassio"),
    "PROT-013": ("asma", "dpoc", "broncoespasmo", "exacerbação", "exacerbacao", "dispneia"),
    "PROT-014": ("dor", "analgesia", "pós-operatório", "pos-operatorio"),
    "PROT-015": ("delirium", "confusão", "confusao", "idoso", "agitação"),
    "PROT-016": (
        "itu",
        "infecção urinária",
        "infeccao urinaria",
        "pielonefrite",
        "cistite",
        "urocultura",
    ),
}


def suggest_protocols(text: str) -> list[str]:
    """Retorna IDs de protocolos cujo gatilho aparece no texto (diagnóstico, queixa, notas)."""
    t = (text or "").lower()
    hits: list[tuple[int, str]] = []
    for pid, kws in PROTOCOL_TRIGGERS.items():
        n = sum(1 for k in kws if k in t)
        if n:
            hits.append((n, pid))
    hits.sort(reverse=True)
    return [pid for _, pid in hits[:4]]


# ---------------------------------------------------------------------------
# Risco consolidado do paciente
# ---------------------------------------------------------------------------
@dataclass
class RiskAssessment:
    level: RiskLevel
    score: int
    factors: list[str] = field(default_factory=list)
    qsofa: int = 0
    news2: int = 0
    critical_findings: list[CriticalFinding] = field(default_factory=list)
    overdue_exams: list[str] = field(default_factory=list)
    protocol_hints: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level,
            "score": self.score,
            "factors": self.factors,
            "qsofa": self.qsofa,
            "news2": self.news2,
            "critical_findings": [c.as_dict() for c in self.critical_findings],
            "overdue_exams": self.overdue_exams,
            "protocol_hints": self.protocol_hints,
        }


def is_overdue(exam: dict[str, Any], now: datetime | None = None) -> bool:
    if exam.get("status") == "atrasado":
        return True
    if exam.get("status") not in ("pendente", "coletado"):
        return False
    due = exam.get("due_at")
    if not due:
        return False
    if isinstance(due, str):
        try:
            due = datetime.fromisoformat(due)
        except ValueError:
            return False
    now = now or datetime.now(tz=due.tzinfo) if due.tzinfo else (now or datetime.now())
    if due.tzinfo and now.tzinfo is None:
        now = now.replace(tzinfo=due.tzinfo)
    return due < now


def assess_risk(
    latest_vital: dict[str, Any] | None,
    exams: list[dict[str, Any]],
    diagnosis_text: str = "",
    age: int | None = None,
    now: datetime | None = None,
) -> RiskAssessment:
    """Combina qSOFA, NEWS2, valores críticos e exames atrasados em um nível de risco.

    Pontuação (didática):
    - NEWS2 ≥ 7 → +4 ; 5-6 → +2 ; qSOFA ≥ 2 → +3
    - cada valor crítico → +3 ; cada atenção → +1
    - cada exame atrasado → +1 (máx. 3)
    - idade ≥ 75 → +1
    Níveis: ≥ 8 crítico · 5-7 alto · 2-4 moderado · < 2 baixo.
    """
    factors: list[str] = []
    score = 0
    q, n2 = 0, 0
    if latest_vital:
        q, qr = qsofa(latest_vital)
        n2, nr = news2(latest_vital)
        if q >= 2:
            score += 3
            factors.append(f"qSOFA {q}/3 ({', '.join(qr)})")
        if n2 >= 7:
            score += 4
            factors.append(f"NEWS2 {n2} (alto): {', '.join(nr)}")
        elif n2 >= 5:
            score += 2
            factors.append(f"NEWS2 {n2} (médio): {', '.join(nr)}")
    crit = evaluate_labs(exams)
    for c in crit:
        if c.severity == "critico":
            score += 3
            factors.append(f"Valor crítico: {c.exam} = {c.value:g} {c.unit} ({c.rule})")
        else:
            score += 1
            factors.append(f"Atenção: {c.exam} = {c.value:g} {c.unit} ({c.rule})")
    overdue = [str(e.get("name")) for e in exams if is_overdue(e, now)]
    if overdue:
        score += min(3, len(overdue))
        factors.append(f"{len(overdue)} exame(s) atrasado(s): {', '.join(overdue[:4])}")
    if age is not None and age >= 75:
        score += 1
        factors.append(f"Idade ≥ 75 anos ({age})")
    level: RiskLevel = (
        "critico" if score >= 8 else "alto" if score >= 5 else "moderado" if score >= 2 else "baixo"
    )
    hints = suggest_protocols(diagnosis_text)
    for c in crit:
        if c.protocol_hint and c.protocol_hint not in hints:
            hints.append(c.protocol_hint)
    return RiskAssessment(level, score, factors, q, n2, crit, overdue, hints)
