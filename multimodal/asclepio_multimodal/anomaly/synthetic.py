"""Geradores sintéticos determinísticos (semente fixa) para sinais vitais, prescrições e mobilidade.

Os cenários casam com ``asclepio_core.synthetic.generate_patients()``: cada paciente recebe uma
semente derivada do prontuário (``mrn``) e, conforme o ``scenario``, uma anomalia plausível
injetada — o gabarito de cada injeção fica em ``PRESCRIPTION_TRUTH`` e ``MOBILITY_TRUTH`` para a
avaliação comparar achados × gabarito.
"""

from __future__ import annotations

import itertools
import random
import re
import zlib
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from ..schemas import MobilityReading, PrescriptionEvent, VitalSample
from .prescriptions import _allergy_hit, match_drug, norm

SEED = 2026

# ---------------------------------------------------------------------------
# Sinais vitais ao vivo
# ---------------------------------------------------------------------------
VITALS_SCENARIOS = ("estavel", "sepse", "dessaturacao")
_BASE = {"hr": 78.0, "sbp": 122.0, "dbp": 74.0, "rr": 16.0, "spo2": 97.0, "temp_c": 36.7}
_NOISE = {"hr": 2.0, "sbp": 3.0, "dbp": 2.0, "rr": 0.8, "spo2": 0.6, "temp_c": 0.05}


def synthetic_onset_index(scenario: str, n: int = 240) -> int | None:
    """Gabarito: índice da amostra em que a anomalia começa (``None`` = cenário estável)."""
    _check(scenario)
    return {"estavel": None, "sepse": n // 2, "dessaturacao": int(n * 0.6)}[scenario]


def synthetic_onset(
    scenario: str, *, start: datetime, step_s: int = 60, n: int = 240
) -> datetime | None:
    i = synthetic_onset_index(scenario, n)
    return None if i is None else start + timedelta(seconds=i * step_s)


def _check(scenario: str) -> None:
    if scenario not in VITALS_SCENARIOS:
        raise ValueError(
            f"Cenário de sinais vitais desconhecido: {scenario!r} ({', '.join(VITALS_SCENARIOS)})"
        )


def synthetic_vitals_stream(
    scenario: str, *, start: datetime, step_s: int = 60, n: int = 240
) -> list[VitalSample]:
    """Série ao vivo: ``estavel``; ``sepse`` (FC↑, PAM↓, FR↑, SpO2↓, T↑ em ~40 min a partir de n/2);
    ``dessaturacao`` (SpO2 cai ~11 pontos em 12 min a partir de 60 % da série)."""
    _check(scenario)
    rng = np.random.default_rng(SEED + zlib.crc32(scenario.encode()))
    onset = synthetic_onset_index(scenario, n)
    minutes = np.arange(n) * step_s / 60
    effect = {k: np.zeros(n) for k in _BASE}
    if onset is not None:
        since = minutes - onset * step_s / 60
        if scenario == "sepse":
            r = np.clip(since / 40, 0, 1)
            for k, d in {
                "hr": 38,
                "sbp": -38,
                "dbp": -18,
                "rr": 10,
                "spo2": -6,
                "temp_c": 1.6,
            }.items():
                effect[k] = d * r
        else:
            r = np.clip(since / 12, 0, 1)
            for k, d in {"spo2": -11, "hr": 10, "rr": 6}.items():
                effect[k] = d * r
    cols: dict[str, np.ndarray] = {}
    for k, base in _BASE.items():
        ar = np.zeros(n)
        e = rng.normal(0, _NOISE[k], n)
        for i in range(
            1, n
        ):  # ruído autocorrelacionado (φ = 0,8): sinais reais não são ruído branco
            ar[i] = 0.8 * ar[i - 1] + e[i] * 0.6
        cols[k] = base + effect[k] + ar
    out = []
    for i in range(n):
        out.append(
            VitalSample(
                at=start + timedelta(seconds=i * step_s),
                hr=round(float(cols["hr"][i])),
                sbp=round(float(cols["sbp"][i])),
                dbp=round(float(cols["dbp"][i])),
                rr=round(float(cols["rr"][i]), 1),
                spo2=min(100, round(float(cols["spo2"][i]))),
                temp_c=round(float(cols["temp_c"][i]), 1),
            )
        )
    return out


# ---------------------------------------------------------------------------
# Prescrições
# ---------------------------------------------------------------------------
# Gabarito: scenario → códigos que a detecção deve apontar (pacientes fora daqui são «normais»).
PRESCRIPTION_TRUTH: dict[str, set[str]] = {
    "sepse_pac": {"prescricao.alergia"},  # piperacilina em alérgica à penicilina
    "sca": {"prescricao.duplicidade"},  # heparina EV somada à enoxaparina
    "hipercalemia_lra": {"prescricao.dose_maxima"},  # KCl 160 mEq/dia em paciente com LRA
    "icc": {"prescricao.suspensao_abrupta"},  # apixabana suspensa sem substituição
    "controle_glicemico": {"prescricao.salto_dose"},  # glargina 14 → 36 UI
    "delirium": {"prescricao.salto_dose"},  # morfina 2 → 10 mg em idoso de 84 anos
    "tev_risco": {
        "prescricao.alergia",
        "prescricao.duplicidade",
    },  # heparina em HIT prévia + fondaparinux
    "dpoc": {"prescricao.suspensao_abrupta"},  # antibiótico suspenso com 1 dia
    "pos_op_estavel": {"prescricao.dose_maxima"},  # dipirona 1 g 4/4 h = 6 g/dia
    "dor_pos_op": {"prescricao.instabilidade"},  # tramadol alterado 4× em 24 h
}


def _naive_like(x: datetime, ref: datetime) -> datetime:
    if x.tzinfo and not ref.tzinfo:
        return x.replace(tzinfo=None)
    if ref.tzinfo and not x.tzinfo:
        return x.replace(tzinfo=ref.tzinfo)
    return x


def _dt(x: Any, ref: datetime) -> datetime:
    return _naive_like(x if isinstance(x, datetime) else datetime.fromisoformat(str(x)), ref)


def _seed(patient: dict[str, Any], salt: str) -> int:
    ident = patient.get("mrn") or patient.get("name") or patient.get("scenario") or ""
    return zlib.crc32(f"{SEED}:{salt}:{ident}".encode())


def parse_dose(text: str | None) -> tuple[float | None, str]:
    """«2 g» → (2.0, 'g'); «1.000 mL» → (1000.0, 'mL'); «875/125 mg» → (875.0, 'mg'); texto livre → (None, '')."""
    m = re.match(r"\s*(\d[\d.,]*)(?:\s*/\s*\d[\d.,]*)?\s*([A-Za-zµ%][^\s,;(]*)", text or "")
    if not m:
        return None, ""
    num = m.group(1)
    if "," in num:
        num = num.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", num):
        num = num.replace(".", "")
    try:
        return float(num), m.group(2)
    except ValueError:
        return None, ""


def generate_prescription_history(
    patient: dict[str, Any], *, now: datetime
) -> list[PrescriptionEvent]:
    """Histórico de ordens do paciente (início, ajustes benignos, suspensões) até ``now``.

    Parte de ``patient['medications']`` (nome, dose, via, frequência, ``started_at``, ``status``) e,
    pelo ``scenario``, injeta a anomalia de ``PRESCRIPTION_TRUTH``. Determinístico por paciente.
    """
    rng = random.Random(_seed(patient, "rx"))
    allergies = list(patient.get("allergies") or [])
    events: list[PrescriptionEvent] = []

    def ev(
        at: datetime,
        drug: str,
        dose: float | None,
        unit: str,
        route: str,
        freq: str,
        action: str,
        note: str | None = None,
        who: str = "Dr. Plantonista",
    ) -> None:
        if at <= now:
            events.append(
                PrescriptionEvent(
                    at=at,
                    drug=drug,
                    dose_value=dose,
                    dose_unit=unit,
                    route=route,
                    frequency=freq,
                    action=action,
                    prescriber=who,
                    note=note,
                )
            )  # type: ignore[arg-type]

    base: dict[str, tuple[Any, ...]] = {}
    for m in patient.get("medications") or []:
        name = str(m.get("name") or "").strip()
        if not name:
            continue
        # ordens que já nascem em conflito com a alergia não fazem parte do histórico «normal»
        if _allergy_hit(norm(name), [norm(a) for a in allergies], allergies):
            continue
        start = _dt(m.get("started_at") or now - timedelta(hours=24), now)
        dose, unit = parse_dose(m.get("dose"))
        route, freq = str(m.get("route") or ""), str(m.get("frequency") or "")
        ev(start, name, dose, unit, route, freq, "inicio")
        base[name] = (start, dose, unit, route, freq, m.get("status"))
        if m.get("status") == "suspenso":
            ev(
                start + timedelta(hours=rng.randint(12, 36)),
                name,
                dose,
                unit,
                route,
                freq,
                "suspensao",
                "Suspenso por evento adverso/decisão clínica",
            )
        elif (
            dose is not None
            and unit in ("mg", "g", "UI", "mcg")
            and "dose unica" not in norm(freq)
            and "bolus" not in norm(freq)
            and now - start >= timedelta(hours=20)
            and rng.random() < 0.3
        ):
            # titulação benigna: ±20–25 %; com teto diário de referência só reduz (nunca passa do máximo)
            capped = (d := match_drug(name)) is not None and d.max_day is not None
            f = rng.choice([0.75, 0.8] if capped else [0.8, 1.2, 1.25])
            ev(
                start + timedelta(hours=rng.randint(10, 18)),
                name,
                round(dose * f, 2),
                unit,
                route,
                freq,
                "ajuste",
                "Ajuste de rotina",
            )

    sc = patient.get("scenario")
    h = lambda x: now - timedelta(hours=x)  # noqa: E731
    if sc == "sepse_pac":
        ev(
            h(2.2),
            "Ceftriaxona",
            2,
            "g",
            "EV",
            "1x/dia",
            "suspensao",
            "Troca para piperacilina-tazobactam",
        )
        ev(
            h(2),
            "Piperacilina-tazobactam",
            4.5,
            "g",
            "EV",
            "6/6h",
            "inicio",
            "Ampliação de espectro",
        )
    elif sc == "sca":
        ev(
            h(1.5),
            "Heparina não fracionada",
            1000,
            "UI/h",
            "EV",
            "contínuo",
            "inicio",
            "Protocolo de SCA",
        )
    elif sc == "hipercalemia_lra":
        ev(h(3), "Cloreto de potássio 19,1%", 40, "mEq", "EV", "6/6h", "inicio", "Reposição")
    elif sc == "icc":
        ev(h(3), "Apixabana", 2.5, "mg", "VO", "12/12h", "suspensao")
    elif sc == "controle_glicemico":
        ev(
            h(2),
            "Insulina glargina",
            36,
            "UI",
            "SC",
            "noite",
            "ajuste",
            "Hiperglicemia persistente",
        )
    elif sc == "delirium":
        ev(h(4), "Morfina", 10, "mg", "EV", "se dor intensa", "ajuste", "Dor refratária")
    elif sc == "tev_risco":
        ev(h(2), "Heparina não fracionada", 5000, "UI", "SC", "8/8h", "inicio", "Profilaxia de TEV")
    elif sc == "dpoc":
        ev(h(1), "Amoxicilina-clavulanato", 875, "mg", "VO", "12/12h", "suspensao")
    elif sc == "pos_op_estavel":
        ev(h(3), "Dipirona", 1, "g", "VO", "4/4h", "ajuste", "Dor controlada parcialmente")
    elif sc == "dor_pos_op":
        for hours_ago, dose in ((20, 75), (15, 100), (9, 75), (3, 100)):
            ev(
                h(hours_ago),
                "Tramadol",
                dose,
                "mg",
                "EV",
                "8/8h",
                "ajuste",
                "Reajuste conforme dor",
            )
    return sorted(events, key=lambda e: e.at)


# ---------------------------------------------------------------------------
# Mobilidade
# ---------------------------------------------------------------------------
MOBILITY_TRUTH: dict[str, set[str]] = {
    "avc": {"mobilidade.imobilidade"},  # 5 h sem mudar de decúbito
    "delirium": {"mobilidade.agitacao_noturna", "mobilidade.saida_leito_noturna"},
    "hipoglicemia": {
        "mobilidade.queda",
        "mobilidade.saida_leito_noturna",
    },  # levantou de madrugada e caiu
    "hipercalemia_lra": {"mobilidade.queda_atividade"},  # atividade despenca à tarde
}
_AMBULATORY = {"pos_op_estavel", "dor_pos_op", "pac_estavel", "hipoglicemia", "itu_complicada"} | {
    f"estavel_{i}" for i in range(1, 9)
}
_BED = ("dorsal", "lateral_esq", "lateral_dir")


def generate_mobility(
    patient: dict[str, Any], *, now: datetime, hours: int = 48
) -> list[MobilityReading]:
    """Leituras a cada 15 min das últimas ``hours`` h até ``now`` (inclusive), com a anomalia do cenário."""
    rng = np.random.default_rng(_seed(patient, "mob"))
    sc = patient.get("scenario")
    age = int(patient.get("age") or 60)
    n = max(int(hours * 4), 8)
    times = [now - timedelta(minutes=15 * (n - 1 - i)) for i in range(n)]
    night = np.array([t.hour >= 22 or t.hour < 6 for t in times])
    level = 0.42 if (sc in _AMBULATORY or (sc is None and age < 70)) else 0.22
    level *= 0.8 if age >= 75 else 1.0
    if sc == "hipercalemia_lra":
        level = 0.32
    # decúbito: troca a cada 75–105 min (margem sob o limite de 2 h do protocolo de reposicionamento)
    pos = np.empty(n, dtype=object)
    cur, left = str(rng.choice(_BED)), int(rng.integers(5, 8))
    turn = np.zeros(n, dtype=bool)
    for i in range(n):
        if left == 0:
            cur, left, turn[i] = (
                str(rng.choice([p for p in _BED if p != cur])),
                int(rng.integers(5, 8)),
                True,
            )
        pos[i] = cur
        left -= 1
    act = np.where(night, np.abs(rng.normal(0.04, 0.03, n)), rng.normal(level, 0.1, n))
    hod = np.array([t.hour + t.minute / 60 for t in times])
    for peak in (8, 12, 18):  # banho e refeições
        act += np.where(~night & (np.abs(hod - peak) < 0.6), 0.15, 0.0)
    act += np.where(turn, 0.12, 0.0)
    in_bed = np.ones(n, dtype=bool)
    day_idx = np.flatnonzero(~night)
    if sc in _AMBULATORY or (sc is None and age < 70):
        for i in rng.choice(day_idx, size=min(len(day_idx), max(n // 12, 1)), replace=False):
            in_bed[i], pos[i], act[i] = False, "em_pe", rng.uniform(0.55, 0.8)
    else:
        for i in day_idx:  # restrito ao leito: refeições sentado
            if 12 <= hod[i] < 13 or 18 <= hod[i] < 19:
                pos[i] = "sentado"

    if sc == "avc":  # imobilidade: 5 h na mesma posição, terminando 3 h antes do fim
        end = max(n - 12, 20)
        pos[end - 20 : end], act[end - 20 : end] = "dorsal", np.abs(rng.normal(0.01, 0.01, 20))
        in_bed[end - 20 : end] = True
    elif sc == "delirium":  # noites agitadas, com saídas do leito
        for i in np.flatnonzero(night):
            act[i] = np.clip(rng.normal(0.65, 0.15), 0.3, 1.0)
            pos[i] = rng.choice(["sentado", "dorsal", "lateral_esq", "lateral_dir"])
        idx = np.flatnonzero(night)
        for k in range(0, len(idx) - 4, 14):
            for i in idx[k + 4 : k + 7]:
                in_bed[i], pos[i] = False, "fora_do_leito"
    elif sc == "hipoglicemia":  # madrugada: levanta e cai
        cand = [i for i in range(n - 4) if times[i].hour == 3 and times[i].minute == 0]
        if cand:
            i = cand[-1]
            for k, (p, ib, a) in enumerate(
                [
                    ("fora_do_leito", False, 0.5),
                    ("em_pe", False, 0.7),
                    ("chao", False, 0.05),
                    ("chao", False, 0.02),
                    ("chao", False, 0.02),
                    ("dorsal", True, 0.2),
                ]
            ):
                if i + k < n:
                    pos[i + k], in_bed[i + k], act[i + k] = p, ib, a
    elif (
        sc == "hipercalemia_lra"
    ):  # atividade diurna despenca por 3 h, mantendo a troca de decúbito
        stretch = [i for i in day_idx if 6 <= hod[i] < 22]
        runs, cur_run = [], [stretch[0]] if stretch else []
        for a, b in itertools.pairwise(stretch):
            if b == a + 1:
                cur_run.append(b)
            else:
                runs.append(cur_run)
                cur_run = [b]
        runs.append(cur_run)
        runs = [r for r in runs if len(r) >= 40]
        if runs:
            blk = runs[-1][-12:]
            for i in blk:
                act[i] = abs(rng.normal(0.03, 0.02))
                pos[i] = "dorsal" if (i // 6) % 2 == 0 else "lateral_esq"
                in_bed[i] = True
    return [
        MobilityReading(
            at=times[i],
            activity=float(np.clip(act[i], 0, 1)),
            position=pos[i],
            in_bed=bool(in_bed[i]),
        )
        for i in range(n)
    ]
