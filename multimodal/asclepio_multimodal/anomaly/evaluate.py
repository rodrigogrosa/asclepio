"""Avaliação da detecção de anomalias — só números medidos, gravados em ``anomaly_eval.json``.

(a) registros reais rotulados do PhysioNet/CinC Challenge 2009 (episódio hipotensivo agudo);
(b) benchmark de injeção controlada sobre linhas de base reais (controles do mesmo desafio);
(c) taxa de alertas por hora antes/depois do antiflood;
(d) prescrições e mobilidade nos 24 pacientes sintéticos × gabarito injetado.
"""

from __future__ import annotations

import json
import platform
import statistics
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np

from ..config import REPO_ROOT
from ..schemas import VitalSample
from . import physionet as pn
from .vitals import METHODS, OnlineVitalsDetector

REPORT = REPO_ROOT / "multimodal" / "reports" / "anomaly_eval.json"
FIG_DIR = REPO_ROOT / "docs" / "assets" / "fase4" / "anomaly"
T_REF = datetime(2026, 1, 1)
WINDOW = (-120, 60)  # minutos em relação a T0: 2 h antes até o fim da janela de previsão
TOL_AFTER = 5  # tolerância (min) para «alerta até 5 min após o início»

METHOD_SETS: dict[str, frozenset[str]] = {
    "limiar": frozenset({"limiar"}),
    "zscore": frozenset({"zscore"}),
    "cusum_ewma": frozenset({"deriva"}),
    "iforest": frozenset({"iforest"}),
    "ensemble": METHODS,
}
METHOD_LABEL = {
    "limiar": "só limiar",
    "zscore": "z-score robusto",
    "cusum_ewma": "CUSUM/EWMA",
    "iforest": "IsolationForest",
    "ensemble": "ensemble",
}
# códigos que sinalizam piora hemodinâmica (o que antecede/acompanha um episódio hipotensivo)
HEMO = {
    "pam_baixa",
    "pas_baixa",
    "indice_choque",
    "mudanca_brusca_map",
    "mudanca_brusca_sbp",
    "deriva_map",
    "deriva_sbp",
    "multivariada",
}
_HR = {"fc_alta", "fc_baixa", "mudanca_brusca_hr", "deriva_hr"}
_MAP = {
    "pam_baixa",
    "pas_baixa",
    "mudanca_brusca_map",
    "mudanca_brusca_sbp",
    "deriva_map",
    "deriva_sbp",
}
_SPO2 = {"spo2_baixa", "mudanca_brusca_spo2", "deriva_spo2"}
_ANY = {"multivariada", "indice_choque", "news2_alto"}
FAMILY: dict[str, set[str]] = {
    "pico_fc": _HR | _ANY,
    "deriva_pam": _MAP | _ANY,
    "dessaturacao": _SPO2 | _ANY,
    "combinacao": _HR | _MAP | _ANY,
}
INJ_LABEL = {
    "pico_fc": "pico de FC",
    "deriva_pam": "deriva de PAM",
    "dessaturacao": "dessaturação",
    "combinacao": "FC↑ + PAM↓",
}


# ---------------------------------------------------------------------------
# utilidades
# ---------------------------------------------------------------------------
def _samples(arr: dict[str, np.ndarray], n: int | None = None) -> list[VitalSample]:
    m = len(arr["t_min"]) if n is None else n
    out = []
    for i in range(m):
        v = {k: (None if np.isnan(arr[k][i]) else float(arr[k][i])) for k in pn.CHANNELS}
        out.append(VitalSample(at=T_REF + timedelta(minutes=i), **v))
    return out


def _run(
    samples: list[VitalSample],
    t0_min: float,
    methods: frozenset[str],
    antiflood: bool = True,
    trace: list[tuple[float, float, int]] | None = None,
) -> list[tuple[float, str, str]]:
    """Alertas (minuto relativo a T0, código sem prefixo, severidade) do detector em fluxo.

    ``trace`` (opcional) recebe (minuto, escore, NEWS2) de cada amostra.
    """
    det = OnlineVitalsDetector(methods=methods, antiflood=antiflood)
    out = []
    for s in samples:
        t = (s.at - T_REF).total_seconds() / 60 + t0_min
        out += [(t, f.code.split(".", 1)[1], f.severity) for f in det.update(s)]
        if trace is not None:
            trace.append((t, det.score, det.news2_score))
    return out


def _wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    """Intervalo de confiança de 95 % (Wilson) para uma proporção k/n."""
    if n == 0:
        return None
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / den
    return [round(max(0.0, c - h), 3), round(min(1.0, c + h), 3)]


def _familia(code: str) -> str:
    if code.startswith("mudanca_brusca"):
        return "zscore"
    if code.startswith("deriva"):
        return "cusum_ewma"
    return "iforest" if code == "multivariada" else "limiar"


def _corroborados(
    alerts: list[tuple[float, str, str]], janela: float = 10
) -> list[tuple[float, str, str]]:
    """Política «2 famílias»: só alerta quando ≥ 2 métodos diferentes concordam em até ``janela`` min."""
    hemo = sorted(a for a in alerts if a[1] in HEMO)
    out, last = [], -1e9
    for i, (t, c, sv) in enumerate(hemo):
        fam = {_familia(c)} | {_familia(c2) for t2, c2, _ in hemo[:i] if t - t2 <= janela}
        if len(fam) >= 2 and t - last >= 15:
            out.append((t, c, sv))
            last = t
    return out


def _valid(x: np.ndarray) -> float:
    return float(np.mean(~np.isnan(x)))


def _version(pkg: str) -> str | None:
    try:
        from importlib.metadata import version

        return version(pkg)
    except Exception:
        return None


def _r(x: float | None, n: int = 3) -> float | None:
    return None if x is None else round(float(x), n)


# ---------------------------------------------------------------------------
# (a) registros reais rotulados
# ---------------------------------------------------------------------------
def load_challenge(log: Any = print) -> list[dict[str, Any]]:
    labels = pn.labels()
    recs = []
    for rid in sorted(labels):
        try:
            d = pn.load_record(rid)
        except Exception as e:  # rede fora do ar, registro ausente…
            log(f"[aviso] registro {rid} indisponível: {type(e).__name__}: {str(e)[:100]}")
            continue
        t = d["t_min"]
        onset = pn.ahe_onset_index(d["map"], from_index=int(np.argmax(t >= 0)))
        recs.append(
            {
                "id": rid,
                "label": labels[rid],
                "set": "A" if rid[0] == "1" else "B",
                "data": d,
                "onset": None if onset is None else float(t[onset]),
            }
        )
    return recs


def score_real(recs: list[dict[str, Any]], method: str, fam: set[str] = HEMO) -> dict[str, Any]:
    tp = tp5 = fn = fp = tn = 0
    leads: list[float] = []
    ctrl_alerts = 0
    for r in recs:
        al = sorted(
            t for t, c, _ in r["alerts"][method] if c in fam and WINDOW[0] <= t <= WINDOW[1]
        )
        if r["label"] == "H":
            end = r["onset"] if r["onset"] is not None else WINDOW[1]
            pre = [t for t in al if t <= end]
            tp += bool(pre)
            tp5 += bool([t for t in al if t <= end + TOL_AFTER])
            fn += not pre
            if pre and r["onset"] is not None:
                leads.append(r["onset"] - pre[0])
        else:
            fp += bool(al)
            tn += not al
            ctrl_alerts += len(al)
    n_h, n_c = tp + fn, fp + tn
    return {
        "n_h": n_h,
        "n_c": n_c,
        "sensibilidade": _r(tp / n_h if n_h else None),
        "sensibilidade_ate_5min_apos": _r(tp5 / n_h if n_h else None),
        "sensibilidade_ic95": _wilson(tp, n_h),
        "especificidade": _r(tn / n_c if n_c else None),
        "especificidade_ic95": _wilson(tn, n_c),
        "precisao": _r(tp / (tp + fp) if tp + fp else None),
        "verdadeiros_positivos": tp,
        "falsos_positivos": fp,
        "falsos_negativos": fn,
        "verdadeiros_negativos": tn,
        "antecedencia_media_min": _r(statistics.mean(leads), 1) if leads else None,
        "antecedencia_mediana_min": _r(statistics.median(leads), 1) if leads else None,
        "antecedencia_max_min": _r(max(leads), 1) if leads else None,
        "alertas_por_controle_na_janela": _r(ctrl_alerts / n_c if n_c else None, 2),
        "n_com_antecedencia": len(leads),
    }


def eval_real(recs: list[dict[str, Any]], log: Any = print) -> dict[str, Any]:
    t = time.time()
    for r in recs:
        smp = _samples(r["data"])
        t0 = float(r["data"]["t_min"][0])
        r["alerts"] = {m: _run(smp, t0, ms) for m, ms in METHOD_SETS.items() if m != "ensemble"}
        r["trace"] = []
        r["alerts"]["ensemble"] = _run(smp, t0, METHODS, trace=r["trace"])
        r["alerts"]["ensemble_critico"] = [a for a in r["alerts"]["ensemble"] if a[2] == "critico"]
        r["alerts"]["ensemble_2_familias"] = _corroborados(r["alerts"]["ensemble"])
        r["alerts_raw"] = _run(smp, t0, METHODS, antiflood=False)
    log(f"  registros reais processados em {time.time() - t:.0f} s")
    out: dict[str, Any] = {
        "conjunto": "PhysioNet/CinC Challenge 2009 — Predicting Acute Hypotensive Episodes (testes A e B)",
        "n_registros": len(recs),
        "n_h": sum(r["label"] == "H" for r in recs),
        "n_c": sum(r["label"] == "C" for r in recs),
        "janela_avaliacao_min_em_relacao_a_T0": list(WINDOW),
        "definicao": (
            "H detectado = alerta hemodinâmico até o início do AHE (≥ 30 min com ≥ 90 % das PAM por "
            "minuto ≤ 60 mmHg, calculado sobre a PAM do registro); C com alerta na janela = falso positivo."
        ),
        "codigos_hemodinamicos": sorted(HEMO),
        "h_sem_inicio_calculavel": [
            r["id"] for r in recs if r["label"] == "H" and r["onset"] is None
        ],
        "metodos": {},
        "metodos_por_conjunto": {"A": {}, "B": {}},
    }
    for m in METHOD_SETS:
        out["metodos"][m] = score_real(recs, m)
        for s in ("A", "B"):
            out["metodos_por_conjunto"][s][m] = score_real([r for r in recs if r["set"] == s], m)
    out["politicas_de_alerta"] = {
        "descricao": (
            "Políticas sobre os alertas do ensemble: «critico» = só severidade crítica; «2 famílias» = só "
            "quando ≥ 2 métodos diferentes (limiar, z-score, CUSUM, IsolationForest) concordam em 10 min."
        ),
        **{m: score_real(recs, m) for m in ("ensemble_critico", "ensemble_2_familias")},
    }
    out["auc_antes_do_inicio"] = _auc(recs)
    out["registros"] = [
        {
            "id": r["id"],
            "rotulo": r["label"],
            "inicio_ahe_min_apos_T0": r["onset"],
            "primeiro_alerta_hemodinamico_ensemble_min": next(
                (t for t, c, _ in sorted(r["alerts"]["ensemble"]) if c in HEMO and t >= WINDOW[0]),
                None,
            ),
        }
        for r in recs
    ]
    return out


def _auc(recs: list[dict[str, Any]]) -> dict[str, Any]:
    """AUC (H × C) de preditores avaliados em [-120, +15] min de T0: nenhum H começou antes de +17 min."""
    from sklearn.metrics import roc_auc_score

    lo, hi = WINDOW[0], 15
    rows = []
    for r in recs:
        if r["label"] == "H" and r["onset"] is None:
            continue
        tr = [(sc, n2) for t, sc, n2 in r["trace"] if lo <= t <= hi]
        d = r["data"]
        sel = (d["t_min"] >= lo) & (d["t_min"] <= hi)
        mp = d["map"][sel]
        rows.append(
            (
                r["label"] == "H",
                r["set"],
                max(sc for sc, _ in tr),
                max(n2 for _, n2 in tr),
                -float(np.nanmin(mp)) if np.any(~np.isnan(mp)) else -float("inf"),
            )
        )
    y = np.array([x[0] for x in rows])
    out: dict[str, Any] = {
        "janela_min": [lo, hi],
        "n_h": int(y.sum()),
        "n_c": int((~y).sum()),
        "nota": "preditor = máximo do escore (ou NEWS2) na janela; «PAM mínima» = −min(PAM), o preditor trivial",
    }
    rng = np.random.default_rng(2026)
    for name, col in (("escore_ensemble", 2), ("news2_maximo", 3), ("pam_minima", 4)):
        x = np.array([row[col] for row in rows], dtype=float)
        x[~np.isfinite(x)] = np.nanmin(x[np.isfinite(x)])
        boots = []
        for _ in range(500):
            i = rng.integers(0, len(y), len(y))
            if 0 < y[i].sum() < len(i):
                boots.append(roc_auc_score(y[i], x[i]))
        out[name] = {
            "auc": _r(roc_auc_score(y, x)),
            "ic95_bootstrap": [_r(np.percentile(boots, 2.5)), _r(np.percentile(boots, 97.5))],
        }
    return out


def eval_antiflood(recs: list[dict[str, Any]]) -> dict[str, Any]:
    def rate(key: str, label: str | None) -> dict[str, Any]:
        sel = [r for r in recs if label is None or r["label"] == label]
        hours = sum(len(r["data"]["t_min"]) for r in sel) / 60
        n = sum(len(r[key]) if key == "alerts_raw" else len(r["alerts"]["ensemble"]) for r in sel)
        return {"alertas": n, "horas": _r(hours, 1), "alertas_por_hora": _r(n / hours, 2)}

    out = {}
    for name, label in (("todos", None), ("controles", "C"), ("episodio_h", "H")):
        antes, depois = rate("alerts_raw", label), rate("alerts", label)
        out[name] = {
            "sem_antiflood": antes,
            "com_antiflood": depois,
            "reducao": _r(
                1 - depois["alertas"] / antes["alertas"] if antes["alertas"] else None, 3
            ),
        }
    out["descricao"] = (
        "sem_antiflood = toda amostra fora do critério vira alerta; com_antiflood = duração mínima "
        "(3 amostras atenção / 2 crítico), histerese com recuperação de 10 min, cooldown de 15 min "
        "com backoff exponencial e supressão de achados redundantes (NEWS2/índice de choque)."
    )
    return out


# ---------------------------------------------------------------------------
# (b) injeção controlada sobre linhas de base reais
# ---------------------------------------------------------------------------
def _ramp(up: int, hold: int, down: int) -> np.ndarray:
    """Perfil 0→1 (subida), 1 (platô) e 1→0 (recuperação)."""
    return np.concatenate(
        [np.linspace(0, 1, up + 1)[1:], np.ones(hold), np.linspace(1, 0, down + 1)[1:-1]]
    )


def _inject(base: dict[str, np.ndarray], kind: str, s: int) -> tuple[dict[str, np.ndarray], int]:
    """Injeta a anomalia ``kind`` a partir do minuto ``s``; devolve a série e o minuto final."""
    out = {k: v.copy() for k, v in base.items()}
    if kind == "pico_fc":
        prof, eff = _ramp(1, 4, 2), {"hr": 40.0}
    elif kind == "deriva_pam":
        prof, eff = _ramp(40, 10, 5), {"map": -22.0, "sbp": -28.0, "dbp": -18.0}
    elif kind == "dessaturacao":
        prof, eff = _ramp(6, 10, 3), {"spo2": -10.0, "rr": 4.0}
    else:  # combinacao: cada sinal moderado, a combinação é que é anômala
        prof, eff = _ramp(20, 10, 5), {"hr": 25.0, "map": -15.0, "sbp": -20.0}
    for k, d in eff.items():
        out[k][s : s + len(prof)] += d * prof
    return out, s + len(prof)


def eval_injection(recs: list[dict[str, Any]], log: Any = print) -> dict[str, Any]:
    bases = []
    for r in recs:
        if r["label"] != "C":
            continue
        d = r["data"]
        pre = np.flatnonzero(d["t_min"] < 0)
        b = {k: d[k][pre] for k in (*pn.CHANNELS, "t_min")}
        if min(_valid(b["hr"]), _valid(b["map"]), _valid(b["sbp"])) >= 0.85:
            bases.append((r["id"], b))
    rng = np.random.default_rng(2026)
    cases: list[tuple[str, dict[str, np.ndarray], list[tuple[str, int, int]]]] = []
    kinds = list(FAMILY)
    for rid, b in bases:
        order = list(rng.permutation(kinds))
        arr, wins = b, []
        for k_i, kind in enumerate(order):
            if kind == "dessaturacao" and _valid(b["spo2"]) < 0.7:
                continue
            s = 100 + 62 * k_i + int(rng.integers(0, 5))
            arr, end = _inject(arr, kind, s)
            wins.append((kind, s, end))
        cases.append((rid, arr, wins))
    n_inj = sum(len(w) for _, _, w in cases)
    log(f"  injeção: {len(cases)} linhas de base reais (controles), {n_inj} anomalias injetadas")

    res: dict[str, Any] = {}
    for m, ms in METHOD_SETS.items():
        per_kind: dict[str, dict[str, list[float]]] = {k: {"hit": [], "delay": []} for k in kinds}
        fp = 0
        for _, arr, wins in cases:
            smp = _samples(arr)
            al = _run(smp, float(arr["t_min"][0]), ms)
            spans = [(s, e + 8) for _, s, e in wins]
            rel = [(t - float(arr["t_min"][0]), c) for t, c, _ in al]
            fp += sum(not any(a <= t <= b for a, b in spans) for t, _ in rel)
            for kind, s, e in wins:
                first = [t for t, c in rel if s <= t <= e + 8 and c in FAMILY[kind]]
                per_kind[kind]["hit"].append(1.0 if first else 0.0)
                if first:
                    per_kind[kind]["delay"].append(min(first) - s)
        tp = int(sum(sum(v["hit"]) for v in per_kind.values()))
        prec = tp / (tp + fp) if tp + fp else None
        rec = tp / n_inj
        delays = [d for v in per_kind.values() for d in v["delay"]]
        res[m] = {
            "verdadeiros_positivos": tp,
            "falsos_negativos": n_inj - tp,
            "falsos_positivos": fp,
            "precisao": _r(prec),
            "recall": _r(rec),
            "f1": _r(2 * prec * rec / (prec + rec) if prec and rec else 0.0),
            "atraso_medio_min": _r(statistics.mean(delays), 1) if delays else None,
            "atraso_mediano_min": _r(statistics.median(delays), 1) if delays else None,
            "por_tipo": {
                k: {
                    "injetadas": len(v["hit"]),
                    "recall": _r(sum(v["hit"]) / len(v["hit"])),
                    "atraso_medio_min": _r(statistics.mean(v["delay"]), 1) if v["delay"] else None,
                }
                for k, v in per_kind.items()
            },
        }
    # ruído das linhas de base sem injeção (alertas/h por método)
    noise = {}
    for m, ms in METHOD_SETS.items():
        n = sum(len(_run(_samples(b), float(b["t_min"][0]), ms)) for _, b in bases)
        noise[m] = _r(n / (len(bases) * 6), 2)
    return {
        "linhas_de_base": [rid for rid, _ in bases],
        "n_linhas_de_base": len(bases),
        "n_anomalias_injetadas": n_inj,
        "tipos": {k: INJ_LABEL[k] for k in kinds},
        "parametros": {
            "pico_fc": "FC +40 bpm por ~6 min",
            "deriva_pam": "PAM −22, PAS −28, PAD −18 mmHg em 40 min, sustentado 10 min",
            "dessaturacao": "SpO2 −10 pontos em 6 min, sustentado 10 min (FR +4)",
            "combinacao": "FC +25 bpm, PAM −15 e PAS −20 mmHg em 20 min, sustentado 10 min",
        },
        "criterio": (
            "TP = alerta de código compatível com o tipo entre o início e o fim da anomalia + 8 min; "
            "FP = qualquer alerta fora das janelas injetadas (inclui eventos fisiológicos reais da linha "
            "de base, portanto a precisão é um piso); atraso = primeiro alerta compatível − início."
        ),
        "metodos": res,
        "ruido_linha_de_base_alertas_por_hora": noise,
    }


# ---------------------------------------------------------------------------
# (d) prescrições e mobilidade × gabarito
# ---------------------------------------------------------------------------
def eval_synthetic(log: Any = print) -> dict[str, Any]:
    from asclepio_core.synthetic import DEFAULT_NOW, generate_patients

    from . import synthetic as syn
    from .mobility import detect_mobility_anomalies
    from .prescriptions import detect_prescription_anomalies

    def run(now: datetime) -> dict[str, dict[str, set[str]]]:
        got: dict[str, dict[str, set[str]]] = {"prescricao": {}, "mobilidade": {}}
        for p in generate_patients(now=now):
            rx = detect_prescription_anomalies(
                syn.generate_prescription_history(p, now=now),
                allergies=p["allergies"],
                weight_kg=p["weight_kg"],
            )
            mob = detect_mobility_anomalies(syn.generate_mobility(p, now=now))
            got["prescricao"][p["scenario"]] = {f.code for f in rx.findings if f.severity != "info"}
            got["mobilidade"][p["scenario"]] = {
                f.code for f in mob.findings if f.severity != "info"
            }
        return got

    def score(
        runs: list[dict[str, dict[str, set[str]]]], mod: str, truth: dict[str, set[str]]
    ) -> dict[str, Any]:
        tp = fp = fn = exact = n = 0
        per_code: dict[str, list[int]] = {}
        wrong = []
        for r in runs:
            for sc, got in r[mod].items():
                want = truth.get(sc, set())
                tp, fp, fn = tp + len(got & want), fp + len(got - want), fn + len(want - got)
                exact += got == want
                n += 1
                for c in got | want:
                    t = per_code.setdefault(c, [0, 0, 0])
                    t[0] += c in got and c in want
                    t[1] += c in got and c not in want
                    t[2] += c not in got and c in want
                if got != want:
                    wrong.append({"cenario": sc, "achados": sorted(got), "gabarito": sorted(want)})
        p, rc = (tp / (tp + fp) if tp + fp else None), (tp / (tp + fn) if tp + fn else None)
        return {
            "pacientes_avaliados": n,
            "pacientes_com_gabarito_exato": exact,
            "verdadeiros_positivos": tp,
            "falsos_positivos": fp,
            "falsos_negativos": fn,
            "precisao": _r(p),
            "recall": _r(rc),
            "f1": _r(2 * p * rc / (p + rc) if p and rc else 0.0),
            "por_codigo": {
                c: {"tp": v[0], "fp": v[1], "fn": v[2]} for c, v in sorted(per_code.items())
            },
            "divergencias": wrong[:12],
        }

    base = run(DEFAULT_NOW)
    sweep_nows = [
        DEFAULT_NOW.replace(hour=14, minute=30),
        DEFAULT_NOW.replace(hour=2, minute=0),
        DEFAULT_NOW.replace(hour=20, minute=45),
        DEFAULT_NOW.replace(month=9, day=3, hour=11),
    ]
    sweep = [base] + [run(n) for n in sweep_nows]
    return {
        "nota": (
            "Gabarito = anomalias injetadas pelos geradores sintéticos; os pacientes sem injeção são «normais». "
            "Valida o pipeline de regras, não a sensibilidade clínica em dados reais."
        ),
        "prescricoes": {
            "24_pacientes": score([base], "prescricao", syn.PRESCRIPTION_TRUTH),
            "varredura_5_horarios": score(sweep, "prescricao", syn.PRESCRIPTION_TRUTH),
            "gabarito_injetado": {k: sorted(v) for k, v in syn.PRESCRIPTION_TRUTH.items()},
        },
        "mobilidade": {
            "24_pacientes": score([base], "mobilidade", syn.MOBILITY_TRUTH),
            "varredura_5_horarios": score(sweep, "mobilidade", syn.MOBILITY_TRUTH),
            "gabarito_injetado": {k: sorted(v) for k, v in syn.MOBILITY_TRUTH.items()},
        },
    }


# ---------------------------------------------------------------------------
# orquestração
# ---------------------------------------------------------------------------
def run_all(*, make_figures: bool = True, log: Any = print) -> dict[str, Any]:
    t0 = time.time()
    log("Carregando registros do PhysioNet (cache em data/datasets/physionet)…")
    recs = load_challenge(log)
    log(f"  {len(recs)} registros")
    report: dict[str, Any] = {
        "gerado_em": datetime.now(UTC).isoformat(timespec="seconds"),
        "ambiente": {"python": platform.python_version(), "sistema": platform.platform()},
        "parametros_do_detector": {
            "janela_zscore_min": 30,
            "z_alerta": 3.5,
            "referencia_cusum_min": 90,
            "cusum_k": 0.5,
            "cusum_h": 4.0,
            "iforest_amostras_linha_de_base": 45,
            "iforest_limite_escore": 0.6,
            "cooldown_min": 15,
            "recuperacao_min": 10,
            "duracao_minima_amostras": {"atencao": 3, "critico": 2},
            "observacao": (
                "Limiares escolhidos a priori (NEWS2/literatura) e conferidos só em séries sintéticas. "
                "Depois de ver a tempestade de alertas em 4 registros reais (101, 106, 201 e 217) foram "
                "acrescentados ao antiflood: recuperação de 10 min, backoff do cooldown e supressão de "
                "NEWS2/índice de choque redundantes. Nenhum parâmetro foi ajustado olhando sensibilidade, "
                "especificidade ou F1 nos registros rotulados nem na injeção."
            ),
        },
        "versoes": {
            pkg: _version(pkg)
            for pkg in ("scikit-learn", "numpy", "scipy", "wfdb", "pandas", "matplotlib")
        },
        "limitacoes": [
            "50 registros de UTI adulta (MIMIC-II): os intervalos de confiança de sensibilidade/especificidade são largos.",
            "O escore do ensemble mistura todos os sinais; não é um preditor dedicado de AHE (ver auc_antes_do_inicio).",
            "Na injeção, FP inclui eventos fisiológicos reais da linha de base: a precisão é um piso.",
            "Prescrições e mobilidade: o gabarito foi injetado pelos mesmos geradores que as regras foram escritas para detectar; valida o pipeline, não a sensibilidade clínica.",
            "O IsolationForest usa as primeiras 45 amostras como linha de base e não recalibra: séries longas com mudança de estado legítima podem gerar alertas.",
            "Doses máximas são referências didáticas de adulto; o protocolo institucional prevalece.",
        ],
    }
    if recs:
        report["physionet_real"] = eval_real(recs, log)
        report["antiflood"] = eval_antiflood(recs)
        report["injecao_controlada"] = eval_injection(recs, log)
    else:
        report["physionet_real"] = {
            "erro": "nenhum registro do PhysioNet disponível (sem rede e sem cache)"
        }
    log("Prescrições e mobilidade (pacientes sintéticos)…")
    report["sinteticos"] = eval_synthetic(log)
    report["tempo_total_s"] = round(time.time() - t0, 1)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    log(f"Relatório: {REPORT}")
    if make_figures:
        from .figures import make_all

        for p in make_all(recs, report, FIG_DIR):
            log(f"Figura: {p}")
    return report
