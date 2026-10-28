"""Anomalias na evolução das prescrições: alterações inesperadas no tratamento.

Regras determinísticas (prescrição segura) + uma pontuação estatística de «mudança inesperada»
em relação ao histórico do próprio paciente:

- ``salto_dose`` — ajuste ≥ 2× (ou ≥ +50 % em medicamento de alta vigilância, ISMP) ou queda ≥ 50 %
  de alta vigilância;
- ``dose_maxima`` — dose diária acima da máxima de referência (tabela ``DRUGS``, adulto);
- ``suspensao_abrupta`` — suspensão sem substituição/desmame de anticoagulante, antibiótico antes
  do curso mínimo, corticoide prolongado ou betabloqueador;
- ``alergia`` — medicamento da classe da alergia registrada (cruzada = atenção);
- ``duplicidade`` — dois medicamentos da mesma classe ativos ao mesmo tempo;
- ``instabilidade`` — ≥ 3 mudanças do mesmo medicamento em 24 h;
- ``mudanca_atipica`` — z-score robusto do tamanho da mudança contra as mudanças anteriores do
  paciente.

As doses máximas são referências didáticas de adulto (bulas ANVISA e diretrizes citadas em
``DRUGS``); o protocolo institucional e o julgamento do prescritor prevalecem.
"""

from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import deque
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from ..schemas import (
    SEVERITY_ORDER,
    AnalysisResult,
    Finding,
    ModelInfo,
    PrescriptionEvent,
    Severity,
)

HIGH_ALERT_JUMP = 1.5  # ≥ +50 % em alta vigilância
JUMP = 2.0  # ≥ 2× nos demais
Z_ATYPICAL = 3.5
INSTABILITY_CHANGES = 3
INSTABILITY_TITRATED = (
    6  # fármacos titulados (vasopressor, insulina em bomba): mudar muito é esperado
)


@dataclass(frozen=True)
class Drug:
    key: str
    aliases: tuple[str, ...]  # trechos do nome, sem acento e em minúsculas
    cls: str  # classe terapêutica (duplicidade)
    high_alert: bool = False
    max_day: float | None = None
    max_unit: str = "mg"  # mg | UI | mEq | mg/kg | UI/kg | mcg/kg/min
    max_abs: float | None = None  # teto absoluto quando o limite é por kg e o peso é desconhecido
    source: str = ""
    keep: str | None = (
        None  # exige continuidade: anticoagulante | antibiotico | corticoide | betabloqueador
    )
    min_course_days: float = 0
    titrated: bool = False


DRUGS: tuple[Drug, ...] = (
    Drug(
        "dipirona",
        ("dipirona", "metamizol"),
        "analgesico_simples",
        max_day=4000,
        source="Bula ANVISA — dipirona sódica: dose única 1 g, máx. 4 g/dia",
    ),
    Drug(
        "paracetamol",
        ("paracetamol", "acetaminofeno"),
        "analgesico_simples",
        max_day=4000,
        source="Bula ANVISA — paracetamol adulto: máx. 4 g/dia (FDA)",
    ),
    Drug(
        "enoxaparina",
        ("enoxaparina",),
        "anticoagulante",
        True,
        2.0,
        "mg/kg",
        200,
        "Bula Clexane: terapêutica 1 mg/kg 12/12 h (2 mg/kg/dia)",
        keep="anticoagulante",
    ),
    Drug(
        "heparina",
        ("heparina",),
        "anticoagulante",
        True,
        40000,
        "UI",
        source="Bula heparina sódica: 20.000–40.000 UI/24 h em infusão contínua",
        keep="anticoagulante",
        titrated=True,
    ),
    Drug("fondaparinux", ("fondaparinux",), "anticoagulante", True, keep="anticoagulante"),
    Drug("apixabana", ("apixabana",), "anticoagulante", True, keep="anticoagulante"),
    Drug("rivaroxabana", ("rivaroxabana",), "anticoagulante", True, keep="anticoagulante"),
    Drug("varfarina", ("varfarina",), "anticoagulante", True, keep="anticoagulante"),
    Drug(
        "insulina_basal",
        ("glargina", "detemir", "degludeca", "insulina nph", " nph"),
        "insulina_basal",
        True,
        1.0,
        "UI/kg",
        100,
        "ADA Standards of Care: dose total típica 0,5–1 UI/kg/dia",
    ),
    Drug(
        "insulina_rapida",
        ("insulina regular", "lispro", "asparte", "glulisina", "escala de correcao"),
        "insulina_rapida",
        True,
        1.0,
        "UI/kg",
        100,
        "ADA Standards of Care: dose total típica 0,5–1 UI/kg/dia",
        titrated=True,
    ),
    Drug(
        "insulina",
        ("insulina",),
        "insulina",
        True,
        1.0,
        "UI/kg",
        100,
        "ADA Standards of Care: dose total típica 0,5–1 UI/kg/dia",
        titrated=True,
    ),
    Drug(
        "morfina",
        ("morfina",),
        "opioide",
        True,
        60,
        "mg",
        source="Bula morfina (Dimorf): 2–10 mg a cada 4 h (≈ 60 mg/dia)",
    ),
    Drug(
        "tramadol",
        ("tramadol",),
        "opioide",
        False,
        400,
        "mg",
        source="Bula ANVISA — tramadol: máx. 400 mg/dia",
    ),
    Drug(
        "cloreto_de_potassio",
        ("cloreto de potassio", "kcl"),
        "potassio",
        True,
        100,
        "mEq",
        source="ISMP (medicamento potencialmente perigoso); ≤ 10 mEq/h periférico, referência 100 mEq/dia",
    ),
    Drug(
        "vancomicina",
        ("vancomicina",),
        "glicopeptideo",
        False,
        4000,
        "mg",
        keep="antibiotico",
        min_course_days=5,
        source="Bula vancomicina: 30 mg/kg/dia, máx. 4 g/dia",
    ),
    Drug(
        "ceftriaxona",
        ("ceftriaxona",),
        "betalactamico",
        False,
        4000,
        "mg",
        keep="antibiotico",
        min_course_days=5,
        source="Bula Rocefin: máx. 4 g/dia",
    ),
    Drug("piperacilina", ("piperacilina",), "betalactamico", keep="antibiotico", min_course_days=5),
    Drug(
        "amoxicilina",
        ("amoxicilina", "ampicilina"),
        "betalactamico",
        keep="antibiotico",
        min_course_days=5,
    ),
    Drug(
        "cefalexina",
        ("cefalexina", "cefazolina", "cefepima", "cefuroxima"),
        "betalactamico",
        keep="antibiotico",
        min_course_days=5,
    ),
    Drug(
        "meropenem",
        ("meropenem", "imipenem"),
        "betalactamico",
        keep="antibiotico",
        min_course_days=5,
    ),
    Drug(
        "azitromicina",
        ("azitromicina", "claritromicina"),
        "macrolideo",
        keep="antibiotico",
        min_course_days=3,
    ),
    Drug(
        "sulfametoxazol",
        ("sulfametoxazol", "trimetoprima", "bactrim"),
        "sulfa",
        keep="antibiotico",
        min_course_days=5,
    ),
    Drug(
        "furosemida",
        ("furosemida",),
        "diuretico_alca",
        False,
        600,
        "mg",
        source="Bula Lasix: máx. 600 mg/dia",
    ),
    Drug(
        "noradrenalina",
        ("noradrenalina", "norepinefrina"),
        "vasopressor",
        True,
        3.0,
        "mcg/kg/min",
        source="Surviving Sepsis Campaign / bula: titular até ≈ 3 mcg/kg/min",
        titrated=True,
    ),
    Drug(
        "nitroprussiato",
        ("nitroprussiato",),
        "vasodilatador",
        True,
        10.0,
        "mcg/kg/min",
        source="Bula Nipride: máx. 10 mcg/kg/min",
        titrated=True,
    ),
    Drug(
        "cetorolaco",
        ("cetorolaco",),
        "aine",
        False,
        120,
        "mg",
        source="Bula cetorolaco: máx. 120 mg/dia, até 5 dias",
    ),
    Drug(
        "ibuprofeno",
        ("ibuprofeno", "diclofenaco", "naproxeno", "cetoprofeno", "nimesulida"),
        "aine",
    ),
    Drug(
        "prednisona",
        ("prednisona", "prednisolona", "metilprednisolona", "dexametasona", "hidrocortisona"),
        "corticoide",
        keep="corticoide",
    ),
    Drug(
        "betabloqueador",
        ("metoprolol", "carvedilol", "atenolol", "propranolol", "bisoprolol"),
        "betabloqueador",
        keep="betabloqueador",
    ),
    Drug("omeprazol", ("omeprazol", "pantoprazol", "esomeprazol"), "ibp"),
    Drug("diazepam", ("diazepam", "midazolam", "lorazepam", "clonazepam"), "benzodiazepinico"),
    Drug("aas", ("acido acetilsalicilico", "aspirina", " aas"), "aas"),
    Drug("clopidogrel", ("clopidogrel", "ticagrelor", "prasugrel"), "p2y12"),
)
SOURCES = {d.key: d.source for d in DRUGS if d.source}

# (palavras da alergia, medicamentos diretos, medicamentos de reatividade cruzada, severidade da cruzada)
# Penicilina × cefalosporina: reatividade cruzada ≈ 1–2 % (cadeias laterais diferentes) → só «info».
_ALLERGIES: tuple[tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...], Severity], ...] = (
    (
        ("penicilina", "betalactam", "beta-lactam"),
        ("penicilina", "amoxicilina", "ampicilina", "piperacilina", "oxacilina", "benzatina"),
        ("ceftriaxona", "cefalexina", "cefazolina", "cefepima", "cefuroxima", "ceftazidima"),
        "info",
    ),
    (("dipirona", "metamizol"), ("dipirona", "metamizol"), (), "info"),
    (
        ("sulfa", "sulfonamida"),
        ("sulfametoxazol", "trimetoprima", "sulfadiazina", "sulfassalazina", "bactrim"),
        (),
        "info",
    ),
    (
        ("aas", "acido acetilsalicilico", "aspirina", "salicilato"),
        ("acido acetilsalicilico", "aspirina", " aas "),
        ("ibuprofeno", "diclofenaco", "cetorolaco", "naproxeno", "cetoprofeno", "nimesulida"),
        "atencao",
    ),
    (
        ("aine", "anti-inflamatorio"),
        (
            "ibuprofeno",
            "diclofenaco",
            "cetorolaco",
            "naproxeno",
            "cetoprofeno",
            "nimesulida",
            "acido acetilsalicilico",
            "aspirina",
        ),
        (),
        "info",
    ),
    (("heparina",), ("heparina", "enoxaparina", "dalteparina", "nadroparina"), (), "info"),
    (
        ("contraste iodado", "iodo"),
        ("iohexol", "iopamidol", "ioversol", "iodixanol", "contraste iodado"),
        (),
        "info",
    ),
    (
        ("opioide", "morfina", "codeina"),
        ("morfina", "codeina", "fentanil", "tramadol", "oxicodona"),
        (),
        "info",
    ),
)

# classe → (severidade da duplicidade, rótulo)
_DUPLICITY: dict[str, tuple[Severity, str]] = {
    "anticoagulante": ("critico", "anticoagulantes"),
    "aine": ("atencao", "anti-inflamatórios"),
    "opioide": ("atencao", "opioides"),
    "ibp": ("atencao", "inibidores de bomba de prótons"),
    "betabloqueador": ("atencao", "betabloqueadores"),
    "betalactamico": ("atencao", "betalactâmicos"),
    "corticoide": ("atencao", "corticoides"),
    "benzodiazepinico": ("atencao", "benzodiazepínicos"),
    "insulina_basal": ("atencao", "insulinas basais"),
    "insulina_rapida": ("atencao", "insulinas rápidas"),
    "analgesico_simples": ("info", "analgésicos/antitérmicos simples"),
}
_JUSTIFIED = (
    "alta",
    "fim do tratamento",
    "fim do curso",
    "descalonamento",
    "troca",
    "reacao",
    "alergia",
    "evento adverso",
    "intoler",
    "contraindic",
    "ciclo completo",
    "curso completo",
)
_PRN = ("se dor", "se febre", "se nausea", "se necess", "acm", "s/n", "sos")


def norm(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)
    )


def match_drug(name: str) -> Drug | None:
    n = f" {norm(name)} "
    for d in DRUGS:
        if any(a in n for a in d.aliases):
            return d
    return None


def _per_day(freq: str) -> float | None:
    """Administrações por dia a partir do texto da frequência (``None`` = não interpretável)."""
    f = norm(freq)
    if m := re.search(r"(\d+)\s*/\s*(\d+)\s*h", f):
        return 24 / max(int(m.group(2)), 1)
    if m := re.search(r"(\d+)\s*x\s*/?\s*(?:ao\s+)?dia", f):
        return float(m.group(1))
    if m := re.search(r"a cada\s*(\d+)\s*(?:h|horas)", f):
        return 24 / max(int(m.group(1)), 1)
    if any(w in f for w in ("dose unica", "unica", "manha", "noite", "diario", "1x")):
        return 1.0
    return None


def _continuous(e: PrescriptionEvent) -> bool:
    f = norm(f"{e.frequency} {e.route}")
    return any(w in f for w in ("continuo", "bomba", "infusao"))


def daily_dose(e: PrescriptionEvent) -> tuple[float, str] | None:
    """Dose diária (ou taxa) na unidade canônica; ``None`` se não for possível calcular."""
    if e.dose_value is None:
        return None
    unit = norm(e.dose_unit).replace(" ", "")
    v = e.dose_value
    if unit in ("g",):
        v, unit = v * 1000, "mg"
    elif unit in ("mcg", "ug", "µg"):
        v, unit = v / 1000, "mg"
    elif unit in ("u", "ui", "un"):
        unit = "ui"
    if unit in ("mcg/kg/min", "ug/kg/min"):
        return v, "mcg/kg/min"  # taxa: compara-se direto com o teto
    if unit in ("ui/h", "mg/h", "meq/h"):
        return v * 24, unit.split("/")[0].replace("ui", "UI").replace("meq", "mEq")
    if unit in ("ui/kg", "mg/kg"):
        n = 1.0 if _continuous(e) else (_per_day(e.frequency) or 1.0)
        return v * n, "UI/kg" if unit == "ui/kg" else "mg/kg"
    n = _per_day(e.frequency)
    if n is None:
        return None
    canon = {"mg": "mg", "ui": "UI", "meq": "mEq"}.get(unit)
    return (v * n, canon) if canon else None


def _max_ratio(
    daily: tuple[float, str], drug: Drug, weight_kg: float | None
) -> tuple[float, float] | None:
    """(razão dose/máximo, máximo na unidade da dose) ou ``None`` se não comparável."""
    if drug.max_day is None:
        return None
    val, unit = daily
    mu = drug.max_unit
    if unit == mu:
        return val / drug.max_day, drug.max_day
    per_kg_units = {"mg/kg": "mg", "UI/kg": "UI"}
    if mu in per_kg_units and unit == per_kg_units[mu]:
        if weight_kg:
            return val / (drug.max_day * weight_kg), drug.max_day * weight_kg
        if drug.max_abs:
            return val / drug.max_abs, drug.max_abs
    return None


def _fmt(v: float) -> str:
    return f"{v:.4g}".replace(".", ",")


class _State:
    """Estado de um medicamento durante o replay das ordens."""

    def __init__(self) -> None:
        self.active = False
        self.started: datetime | None = None
        self.daily: tuple[float, str] | None = None
        self.raw: tuple[float, str] | None = None
        self.peak: float = 0.0
        self.changes: deque[datetime] = deque()
        self.max_flagged = 0.0
        self.last_unstable: datetime | None = None
        self.name = ""


def _f(
    code: str,
    title: str,
    desc: str,
    sev: Severity,
    at: datetime,
    score: float,
    evidence: dict[str, Any],
    rec: str,
) -> Finding:
    return Finding(
        code=code,
        title=title,
        description=desc,
        severity=sev,
        modality="prescricao",
        score=score,
        at=at,
        evidence=evidence,
        recommendation=rec,
    )


def detect_prescription_anomalies(
    events: list[PrescriptionEvent],
    *,
    allergies: Sequence[str] = (),
    weight_kg: float | None = None,
) -> AnalysisResult:
    """Reproduz as ordens em ordem cronológica e aponta o que foge da prescrição segura."""
    ordered = sorted(events, key=lambda e: e.at)
    allergens = [norm(a) for a in allergies]
    state: dict[str, _State] = {}
    findings: list[Finding] = []
    log_ratios: list[float] = []  # histórico de mudanças do paciente (|ln razão|)
    allergy_flagged: set[str] = set()
    series: dict[str, list[Any]] = {
        k: [] for k in ("t", "drug", "dose_diaria", "unidade", "acao", "surpresa", "alerta")
    }
    marked: list[int] = []

    def active_in_class(cls: str, except_key: str) -> list[str]:
        return [
            s.name
            for k, s in state.items()
            if s.active
            and k != except_key
            and (d := match_drug(s.name)) is not None
            and d.cls == cls
        ]

    for idx, e in enumerate(ordered):
        drug = match_drug(e.drug)
        key = drug.key if drug else norm(e.drug).split("(")[0].strip()
        st = state.setdefault(key, _State())
        st.name = e.drug
        daily = daily_dose(e)
        raw = (e.dose_value, norm(e.dose_unit)) if e.dose_value is not None else None
        new: list[Finding] = []
        surprise = 0.0
        prescribing = e.action != "suspensao"
        label = f"{e.drug}" + (
            f" {_fmt(e.dose_value)} {e.dose_unit}" if e.dose_value is not None else ""
        )

        # --- alergia (uma vez por medicamento)
        if prescribing and key not in allergy_flagged:
            hit = _allergy_hit(norm(e.drug), allergens, allergies)
            if hit:
                kind, allergy, cross_sev = hit
                allergy_flagged.add(key)
                if kind == "direta":
                    new.append(
                        _f(
                            "prescricao.alergia",
                            f"Alergia registrada: {e.drug}",
                            f"{e.drug} pertence à classe da alergia «{allergy}» registrada no prontuário.",
                            "critico",
                            e.at,
                            0.95,
                            {"medicamento": e.drug, "alergia": allergy, "tipo": kind},
                            "Suspender a ordem e contatar o prescritor e a farmácia clínica antes da próxima dose.",
                        )
                    )
                else:
                    new.append(
                        _f(
                            "prescricao.alergia",
                            f"Possível reação cruzada: {e.drug}",
                            f"{e.drug} tem reatividade cruzada com a alergia «{allergy}» (risco baixo, mas real).",
                            cross_sev,
                            e.at,
                            0.55 if cross_sev != "info" else 0.15,
                            {"medicamento": e.drug, "alergia": allergy, "tipo": kind},
                            "Confirmar a história alérgica com o paciente e o prescritor; monitorar na primeira dose.",
                        )
                    )

        # --- dose máxima diária
        if prescribing and drug and daily:
            mr = _max_ratio(daily, drug, weight_kg)
            if mr and mr[0] > 1.0 and daily[0] > st.max_flagged * 1.05:
                st.max_flagged = daily[0]
                sev: Severity = "critico" if mr[0] >= 1.5 or drug.high_alert else "atencao"
                new.append(
                    _f(
                        "prescricao.dose_maxima",
                        f"Dose acima da máxima diária: {e.drug}",
                        f"{label} {e.frequency} equivale a {_fmt(daily[0])} {daily[1]}/dia, "
                        f"{mr[0]:.1f}× o máximo de referência ({_fmt(mr[1])} {daily[1]}/dia). Fonte: {drug.source}.",
                        sev,
                        e.at,
                        round(min(1.0, 0.5 + 0.25 * mr[0]), 2),
                        {
                            "medicamento": e.drug,
                            "dose_diaria": round(daily[0], 2),
                            "maximo_diario": round(mr[1], 2),
                            "unidade": daily[1],
                            "razao": round(mr[0], 2),
                        },
                        "Revisar a dose com o prescritor e a farmácia; conferir peso e função renal/hepática.",
                    )
                )

        # --- salto de dose + mudança atípica (só em ajuste)
        if e.action == "ajuste" and st.active:
            ratio = _ratio(st, daily, raw)
            if ratio:
                lr = abs(math.log(ratio))
                hv = bool(drug and drug.high_alert)
                up = ratio >= (HIGH_ALERT_JUMP if hv else JUMP)
                down = hv and ratio <= 1 / JUMP
                if up or down:
                    big = ratio >= JUMP or ratio <= 1 / JUMP
                    sev = "critico" if (big and hv) or ratio >= 2 * JUMP else "atencao"
                    prev = st.daily or st.raw
                    new.append(
                        _f(
                            "prescricao.salto_dose",
                            f"{'Salto' if up else 'Queda abrupta'} de dose: {e.drug} ×{ratio:.1f}",
                            f"A dose de {e.drug} {'subiu' if up else 'caiu'} ×{ratio:.2f} de uma vez"
                            f"{' (medicamento de alta vigilância)' if hv else ''}.",
                            sev,
                            e.at,
                            round(min(1.0, 0.4 + 0.2 * max(ratio, 1 / ratio)), 2),
                            {
                                "medicamento": e.drug,
                                "dose_anterior": round(prev[0], 3) if prev else None,
                                "dose_nova": round((daily or raw)[0], 3),
                                "razao": round(ratio, 2),
                                "alta_vigilancia": hv,
                            },
                            "Confirmar com o prescritor se a mudança é intencional (titulação/protocolo) antes de administrar.",
                        )
                    )
                surprise = _surprise(lr, log_ratios)
                if surprise >= 1 - math.exp(-Z_ATYPICAL / 4) and not any(
                    f.code == "prescricao.salto_dose" for f in new
                ):
                    new.append(
                        _f(
                            "prescricao.mudanca_atipica",
                            f"Mudança atípica para este paciente: {e.drug}",
                            f"O tamanho desta mudança (×{ratio:.2f}) foge do padrão das alterações anteriores deste paciente.",
                            "atencao",
                            e.at,
                            round(surprise, 2),
                            {
                                "medicamento": e.drug,
                                "razao": round(ratio, 2),
                                "surpresa": round(surprise, 2),
                                "mudancas_anteriores": len(log_ratios),
                            },
                            "Conferir se a alteração foi intencional e registrada na evolução.",
                        )
                    )
                log_ratios.append(lr)

        # --- suspensão abrupta
        if e.action == "suspensao" and st.active and drug and drug.keep:
            f = _abrupt(e, st, drug, state, ordered, idx)
            if f:
                new.append(f)

        # --- duplicidade (ao ativar um medicamento)
        if prescribing and not st.active and drug and drug.cls in _DUPLICITY:
            others = active_in_class(drug.cls, key)
            if others:
                sev, cls_label = _DUPLICITY[drug.cls]
                new.append(
                    _f(
                        "prescricao.duplicidade",
                        f"Duplicidade terapêutica: {cls_label}",
                        f"{e.drug} foi iniciado com {', '.join(others)} ainda ativo(s): mesma classe ({cls_label}).",
                        sev,
                        e.at,
                        0.9 if sev == "critico" else 0.55 if sev == "atencao" else 0.2,
                        {"medicamento": e.drug, "ja_ativos": others, "classe": drug.cls},
                        "Confirmar a intenção terapêutica; se for troca, suspender o anterior para evitar sobreposição.",
                    )
                )

        # --- instabilidade (mudanças repetidas do mesmo medicamento em 24 h)
        restart = e.action == "inicio" and st.started is not None and not st.active
        if e.action in ("ajuste", "suspensao") or restart:
            st.changes.append(e.at)
            while st.changes and e.at - st.changes[0] > timedelta(hours=24):
                st.changes.popleft()
            limit = INSTABILITY_TITRATED if (drug and drug.titrated) else INSTABILITY_CHANGES
            if len(st.changes) >= limit and (
                st.last_unstable is None or e.at - st.last_unstable > timedelta(hours=24)
            ):
                st.last_unstable = e.at
                new.append(
                    _f(
                        "prescricao.instabilidade",
                        f"Tratamento instável: {e.drug}",
                        f"{len(st.changes)} mudanças de {e.drug} em 24 h — titulação sem estabilizar.",
                        "atencao",
                        e.at,
                        0.6,
                        {"medicamento": e.drug, "mudancas_24h": len(st.changes)},
                        "Discutir o plano terapêutico com a equipe; considerar protocolo de titulação ou reavaliar o diagnóstico.",
                    )
                )

        # --- atualiza o estado
        if e.action == "suspensao":
            st.active = False
        else:
            if (e.action == "inicio" and not st.active) or st.started is None:
                st.started = e.at  # (re)início de curso
            st.active = True
            if daily or raw:
                st.daily, st.raw = daily, raw
                st.peak = max(st.peak, (daily or raw)[0])
        findings += new
        if new:
            marked.append(idx)
        series["t"].append(e.at.isoformat())
        series["drug"].append(e.drug)
        series["dose_diaria"].append(None if not (daily or raw) else round((daily or raw)[0], 3))
        series["unidade"].append(daily[1] if daily else (e.dose_unit if raw else None))
        series["acao"].append(e.action)
        series["surpresa"].append(round(surprise, 3))
        series["alerta"].append(
            max((f.severity for f in new), key=lambda s: SEVERITY_ORDER[s], default="")
        )
    series["anomaly_index"] = marked
    series["anomaly_at"] = [series["t"][i] for i in marked]

    alerts = [f for f in findings if f.severity != "info"]
    n_crit = sum(f.severity == "critico" for f in findings)
    risk = 0.0
    if alerts:
        risk = min(1.0, max(f.score for f in alerts) + 0.05 * (len(alerts) - 1))
    if alerts:
        worst = max(alerts, key=lambda f: (SEVERITY_ORDER[f.severity], f.score))
        summary = (
            f"{len(alerts)} {'alteração inesperada' if len(alerts) == 1 else 'alterações inesperadas'} na "
            f"prescrição ({n_crit} {'crítica' if n_crit == 1 else 'críticas'}). "
            f"Mais grave: {worst.title}."
        )
    else:
        summary = f"Sem alterações inesperadas em {len(ordered)} {'ordem' if len(ordered) == 1 else 'ordens'} de prescrição."
    used = {m.key for e in ordered if (m := match_drug(e.drug))}
    by_code: dict[str, int] = {}
    for f in alerts:
        by_code[f.code] = by_code.get(f.code, 0) + 1
    return AnalysisResult(
        kind="prescricao",
        summary=summary,
        risk_score=round(risk, 3),
        findings=findings,
        metrics={
            "ordens": len(ordered),
            "medicamentos": len(state),
            "alertas": len(alerts),
            "alertas_criticos": n_crit,
            "alertas_por_codigo": by_code,
            "mudancas_de_dose": sum(e.action == "ajuste" for e in ordered),
        },
        series=series,
        details={"referencias": {k: SOURCES[k] for k in sorted(used) if k in SOURCES}},
        models=[
            ModelInfo(
                name="Prescrição segura: doses máximas, alergias, duplicidades e continuidade",
                task="detecção de anomalias",
                provider="regra",
                details={
                    "medicamentos_na_tabela": len(DRUGS),
                    "salto_alta_vigilancia": HIGH_ALERT_JUMP,
                    "salto_demais": JUMP,
                },
            ),
            ModelInfo(
                name="Z-score robusto da mudança de dose (histórico do paciente)",
                task="mudança inesperada",
                provider="regra",
                details={"z_limite": Z_ATYPICAL},
            ),
        ],
        warnings=([] if ordered else ["Sem ordens de prescrição"])
        + (["Peso desconhecido: limites por kg usam o teto absoluto"] if weight_kg is None else []),
    ).finalize()


def _allergy_hit(
    drug_norm: str, allergens: list[str], raw: Sequence[str]
) -> tuple[str, str, Severity] | None:
    n = f" {drug_norm} "
    for a, original in zip(allergens, raw, strict=False):
        for words, direct, cross, cross_sev in _ALLERGIES:
            if not any(w in a for w in words):
                continue
            if any(d in n for d in direct):
                return "direta", original, "critico"
            if any(c in n for c in cross):
                return "cruzada", original, cross_sev
    return None


def _ratio(
    st: _State, daily: tuple[float, str] | None, raw: tuple[float, str] | None
) -> float | None:
    if daily and st.daily and daily[1] == st.daily[1] and st.daily[0] > 0:
        return daily[0] / st.daily[0]
    if raw and st.raw and raw[1] == st.raw[1] and st.raw[0] > 0:
        return raw[0] / st.raw[0]
    return None


def _surprise(lr: float, history: list[float]) -> float:
    """0..1: quão fora do padrão de mudanças do paciente (z robusto de |ln razão|)."""
    if len(history) >= 3:
        med = statistics.median(history)
        scale = max(1.4826 * statistics.median(abs(h - med) for h in history), 0.15)
    else:
        med, scale = 0.0, 0.25  # a priori: titulações habituais mudam ~25 %
    z = max(0.0, (lr - med) / scale)
    return 1 - math.exp(-z / 4)


def _abrupt(
    e: PrescriptionEvent,
    st: _State,
    drug: Drug,
    state: dict[str, _State],
    ordered: list[PrescriptionEvent],
    idx: int,
) -> Finding | None:
    """Suspensão sem substituição, desmame ou justificativa de um medicamento que exige continuidade."""
    note = norm(e.note or "")
    if any(w in note for w in _JUSTIFIED):
        return None
    # substituição: outro medicamento da mesma classe iniciado até 12 h antes/depois
    for o in ordered:
        d = match_drug(o.drug)
        if (
            d
            and d.keep == drug.keep
            and d.key != drug.key
            and o.action in ("inicio", "ajuste")
            and abs((o.at - e.at).total_seconds()) <= 12 * 3600
        ):
            return None
    days = (e.at - st.started).total_seconds() / 86400 if st.started else 0.0
    last = (st.daily or st.raw or (0.0, ""))[0]
    tapered = st.peak > 0 and last <= 0.5 * st.peak
    if drug.keep in ("corticoide", "betabloqueador") and tapered:
        return None
    if drug.keep == "antibiotico" and days >= drug.min_course_days:
        return None
    if drug.keep == "corticoide" and days < 7:
        return None
    if drug.keep == "betabloqueador" and days < 1:
        return None
    why = {
        "anticoagulante": "risco de evento tromboembólico",
        "antibiotico": f"curso interrompido com {days:.1f} dia(s) (mínimo de referência {drug.min_course_days:g})",
        "corticoide": f"uso por {days:.0f} dias sem desmame: risco de insuficiência adrenal",
        "betabloqueador": "risco de taquicardia/isquemia de rebote sem desmame",
    }[drug.keep or ""]
    sev: Severity = "critico" if drug.keep == "anticoagulante" else "atencao"
    return _f(
        "prescricao.suspensao_abrupta",
        f"Suspensão abrupta: {e.drug}",
        f"{e.drug} foi suspenso sem substituição, desmame ou justificativa registrada — {why}.",
        sev,
        e.at,
        0.85 if sev == "critico" else 0.6,
        {"medicamento": e.drug, "dias_de_uso": round(days, 2), "classe_continuidade": drug.keep},
        "Confirmar com o prescritor se a suspensão é intencional; se não for, restabelecer a prescrição.",
    )
