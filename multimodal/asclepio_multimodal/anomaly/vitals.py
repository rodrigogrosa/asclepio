"""Anomalias em séries de sinais vitais (batimentos, pressão arterial, oxigenação, respiração, T°).

``OnlineVitalsDetector`` processa uma amostra por vez (monitor ao vivo) e combina quatro famílias:

1. **limiar** — limites fisiológicos alinhados ao NEWS2/qSOFA de ``asclepio_core.clinical_rules``,
   NEWS2 composto e índice de choque (FC/PAS); a PAM é derivada quando não vem medida;
2. **zscore** — z-score robusto (mediana/MAD) em janela móvel: mudanças bruscas;
3. **deriva** — CUSUM bilateral sobre a série suavizada (EWMA) contra a referência dos últimos
   90 min: deriva lenta (queda progressiva de SpO2 ou PAM) que nenhum limite pega a tempo;
4. **iforest** — IsolationForest multivariado ajustado na linha de base do próprio paciente
   (primeiras ``baseline_n`` amostras): combinações anômalas (ex.: FC↑ + PAM↓ ainda dentro dos
   limites individuais).

Antiflood (``antiflood=True``): duração mínima (3 amostras em ``atencao``, 2 em ``critico``),
histerese (o alerta só se rearma depois que o valor folga do limiar) e cooldown por código
(15 min), com escalonamento imediato de ``atencao`` para ``critico``. Cadência nominal: 1
amostra/min — amostras com menos de 20 s da anterior são ignoradas.
"""

from __future__ import annotations

import math
import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from asclepio_core.clinical_rules import news2

from ..schemas import SEVERITY_ORDER, AnalysisResult, Finding, ModelInfo, Severity, VitalSample

METHODS = frozenset({"limiar", "zscore", "deriva", "iforest"})
MAD_TO_SD = 1.4826


@dataclass(frozen=True)
class _Sig:
    label: str
    unit: str
    floor: float  # menor escala robusta aceitável: sinal quase constante não gera z gigante
    min_change: float  # variação absoluta mínima para o desvio importar clinicamente
    abrupt: int  # direção que preocupa na mudança brusca (0 = ambas)
    drift: int  # idem para a deriva


_SIG: dict[str, _Sig] = {
    "hr": _Sig("frequência cardíaca", "bpm", 2.0, 15.0, 0, 0),
    "sbp": _Sig("pressão sistólica", "mmHg", 4.0, 15.0, 0, -1),
    "map": _Sig("PAM", "mmHg", 3.0, 10.0, 0, -1),
    "rr": _Sig("frequência respiratória", "irpm", 1.5, 5.0, 1, 1),
    "spo2": _Sig("SpO2", "%", 0.8, 3.0, -1, -1),
    "temp_c": _Sig("temperatura", "°C", 0.15, 0.8, 1, 1),
}


@dataclass(frozen=True)
class _Ladder:
    """Degraus de severidade de um parâmetro: ``steps`` do mais brando ao mais grave."""

    code: str
    sig: str
    dir: int  # -1: alerta quando cai até o limiar; +1: quando sobe
    steps: tuple[tuple[float, Severity], ...]
    margin: float  # histerese: só «recupera» depois de folgar do degrau mais brando
    title: str
    unit: str
    ref: str
    rec: str


_HIPOXEMIA = (
    "Conferir sensor e perfusão, posicionar o paciente, avaliar O2 suplementar e acionar o médico."
)
_PA_BAIXA = (
    "Reavaliar volemia e perfusão, conferir manguito/cateter e acionar o médico; "
    "se houver febre ou taquicardia, abrir o protocolo de sepse (PROT-001)."
)
_LADDERS: tuple[_Ladder, ...] = (
    _Ladder(
        "spo2_baixa",
        "spo2",
        -1,
        ((93, "atencao"), (91, "critico")),
        2,
        "SpO2 baixa",
        "%",
        "NEWS2: SpO2 ≤ 93 % = 2 pontos; ≤ 91 % = 3 pontos",
        _HIPOXEMIA,
    ),
    _Ladder(
        "pam_baixa",
        "map",
        -1,
        ((65, "atencao"), (60, "critico")),
        3,
        "PAM baixa",
        "mmHg",
        "Alvo de PAM ≥ 65 mmHg (Sepsis-3); ≤ 60 mmHg é o limiar do episódio hipotensivo agudo",
        _PA_BAIXA,
    ),
    _Ladder(
        "pas_baixa",
        "sbp",
        -1,
        ((100, "atencao"), (90, "critico")),
        4,
        "PAS baixa",
        "mmHg",
        "qSOFA: PAS ≤ 100; NEWS2: ≤ 90 = 3 pontos",
        _PA_BAIXA,
    ),
    _Ladder(
        "pas_alta",
        "sbp",
        1,
        ((180, "atencao"), (220, "critico")),
        10,
        "PAS elevada",
        "mmHg",
        "PROT-008: PAS ≥ 180 = crise hipertensiva; NEWS2: ≥ 220 = 3 pontos",
        "Repetir a medida, avaliar sintomas de órgão-alvo e seguir o protocolo de crise hipertensiva (PROT-008).",
    ),
    _Ladder(
        "fc_alta",
        "hr",
        1,
        ((111, "atencao"), (131, "critico")),
        5,
        "Taquicardia",
        "bpm",
        "NEWS2: FC 111–130 = 2 pontos; ≥ 131 = 3 pontos",
        "Checar ritmo (ECG), dor, febre, volemia e sangramento; acionar o médico se persistir.",
    ),
    _Ladder(
        "fc_baixa",
        "hr",
        -1,
        ((50, "atencao"), (40, "critico")),
        4,
        "Bradicardia",
        "bpm",
        "NEWS2: FC ≤ 40 = 3 pontos",
        "Checar ECG, perfusão e fármacos cronotrópicos negativos; acionar o médico.",
    ),
    _Ladder(
        "fr_alta",
        "rr",
        1,
        ((21, "atencao"), (25, "critico")),
        2,
        "Taquipneia",
        "irpm",
        "NEWS2: FR 21–24 = 2 pontos; ≥ 25 = 3 pontos; qSOFA: FR ≥ 22",
        "Avaliar esforço respiratório, SpO2 e causa (infecção, dor, acidose); acionar o médico.",
    ),
    _Ladder(
        "fr_baixa",
        "rr",
        -1,
        ((11, "atencao"), (8, "critico")),
        1.5,
        "Bradipneia",
        "irpm",
        "NEWS2: FR ≤ 8 = 3 pontos",
        "Avaliar nível de consciência e sedação/opioides; acionar o médico.",
    ),
    _Ladder(
        "temp_alta",
        "temp_c",
        1,
        ((38.5, "atencao"), (40.5, "critico")),
        0.4,
        "Febre",
        "°C",
        "Febre ≥ 38,5 °C; hiperpirexia ≥ 40,5 °C",
        "Investigar foco infeccioso, coletar culturas se indicado e considerar antitérmico.",
    ),
    _Ladder(
        "temp_baixa",
        "temp_c",
        -1,
        ((35.5, "atencao"), (35.0, "critico")),
        0.4,
        "Hipotermia",
        "°C",
        "NEWS2: T ≤ 35,0 °C = 3 pontos",
        "Aquecer o paciente e investigar sepse/endocrinopatia.",
    ),
    _Ladder(
        "indice_choque",
        "si",
        1,
        ((0.9, "atencao"), (1.0, "critico")),
        0.05,
        "Índice de choque elevado",
        "",
        "Índice de choque (FC/PAS) normal 0,5–0,7; ≥ 0,9 sugere hipoperfusão; ≥ 1,0 choque",
        _PA_BAIXA,
    ),
    _Ladder(
        "news2_alto",
        "news2",
        1,
        ((5, "atencao"), (7, "critico")),
        1,
        "NEWS2 elevado",
        "pontos",
        "NEWS2 5–6 = risco médio; ≥ 7 = risco alto (RCP/NHS)",
        "Reavaliação médica imediata e aumento da frequência de monitorização.",
    ),
)

# resumos que não acrescentam nada quando o parâmetro que os causa já está em alerta
_REDUNDANT = {
    "indice_choque": ("pas_baixa", "pam_baixa"),
    "news2_alto": tuple(lad.code for lad in _LADDERS if lad.code != "news2_alto"),
}
_REC_ABRUPTA = (
    "Conferir o sensor e o paciente à beira-leito; se a mudança for real, acionar o médico."
)
_REC_DERIVA = "Tendência sustentada: reavaliar o paciente agora, antes de cruzar o limite clínico."


@dataclass
class _Gate:
    run_att: int = 0
    run_crit: int = 0
    active: bool = False
    sev: Severity = "info"
    last_emit: datetime | None = None
    cool: timedelta | None = None  # cooldown atual: dobra a cada reincidência crônica
    clear_since: datetime | None = None  # desde quando o valor está fora da faixa de alerta


def _mad_scale(xs: list[float], floor: float) -> tuple[float, float]:
    med = statistics.median(xs)
    mad = statistics.median(abs(x - med) for x in xs)
    return med, max(MAD_TO_SD * mad, floor)


def _num(x: float | None) -> float | None:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def derived_map(s: VitalSample) -> float | None:
    """PAM medida ou, na falta, DIA + (SIS − DIA)/3."""
    m = _num(s.map)
    if m is not None:
        return m
    sbp, dbp = _num(s.sbp), _num(s.dbp)
    return None if sbp is None or dbp is None else dbp + (sbp - dbp) / 3


class OnlineVitalsDetector:
    """Detector em fluxo, um por paciente (estado em memória). ``update`` → achados; ``score`` 0..1."""

    def __init__(
        self,
        *,
        methods: frozenset[str] | set[str] = METHODS,
        antiflood: bool = True,
        baseline_n: int = 45,
        window_min: float = 30,
        ref_min: float = 90,
        cooldown_min: float = 15,
        recover_min: float = 10,
        min_step_s: float = 20,
        z_alert: float = 3.5,
        cusum_k: float = 0.5,
        cusum_h: float = 4.0,
        if_threshold: float = 0.6,
        random_state: int = 0,
    ) -> None:
        self.methods = frozenset(methods)
        self.antiflood = antiflood
        self.baseline_n = baseline_n
        self.window = timedelta(minutes=window_min)
        self.ref = timedelta(minutes=ref_min)
        self.lag = timedelta(minutes=15)
        self.cooldown = timedelta(minutes=cooldown_min)
        self.recover = timedelta(minutes=recover_min)
        self.min_step_s = min_step_s
        self.z_alert, self.k, self.h = z_alert, cusum_k, cusum_h
        self.if_threshold = if_threshold
        self.random_state = random_state
        self.min_run = {"atencao": 3, "critico": 2}
        self.reset()

    # ------------------------------------------------------------------ estado
    def reset(self) -> None:
        self.score = 0.0
        self.n_samples = 0
        self.news2_score = 0
        self.last_at: datetime | None = None
        self._gates: dict[str, _Gate] = {}
        self._win: dict[str, deque[tuple[datetime, float]]] = {s: deque() for s in _SIG}
        self._ref: dict[str, deque[tuple[datetime, float]]] = {s: deque() for s in _SIG}
        self._ewma: dict[str, float] = {}
        self._cusum: dict[str, list[float]] = {s: [0.0, 0.0] for s in _SIG}
        self._base_rows: list[list[float | None]] = []
        self._if: Any = None
        self._if_cols: list[str] = []
        self._if_med: dict[str, float] = {}
        self._if_sd: dict[str, float] = {}

    @property
    def active_codes(self) -> list[str]:
        return sorted(c for c, g in self._gates.items() if g.active)

    def _reset_windows(self) -> None:
        for s in _SIG:
            self._win[s].clear()
            self._ref[s].clear()
            self._cusum[s] = [0.0, 0.0]
        self._ewma.clear()

    # ------------------------------------------------------------------ antiflood
    def _gate(self, code: str, sev: Severity | None, hold: bool, now: datetime) -> Severity | None:
        """Máquina de estados de um código: devolve a severidade a emitir, ou ``None``."""
        if not self.antiflood:
            return sev
        g = self._gates.setdefault(code, _Gate())
        g.run_att = g.run_att + 1 if sev else 0
        g.run_crit = g.run_crit + 1 if sev == "critico" else 0
        if g.active:  # histerese: só desativa depois de ficar fora da faixa por `recover` seguidos
            g.clear_since = None if hold else (g.clear_since or now)
            if g.clear_since is not None and now - g.clear_since >= self.recover:
                g.active, g.clear_since = False, None
        cand: Severity | None = (
            "critico"
            if g.run_crit >= self.min_run["critico"]
            else "atencao"
            if g.run_att >= self.min_run["atencao"]
            else None
        )
        if cand is None:
            return None
        if g.active:  # já alertado: só escalona
            if SEVERITY_ORDER[cand] > SEVERITY_ORDER[g.sev]:
                g.sev, g.last_emit = cand, now
                return cand
            return None
        cool = g.cool or self.cooldown
        if g.last_emit is not None and now - g.last_emit < cool:
            return None
        # reincidência crônica (volta antes de 4× o cooldown): dobra o cooldown, até 8×; sossegou → volta ao base
        chronic = g.last_emit is not None and now - g.last_emit < 4 * cool
        g.cool = min(2 * cool, 8 * self.cooldown) if chronic else self.cooldown
        g.active, g.sev, g.last_emit = True, cand, now
        return cand

    def _covered(self, code: str, sev: Severity) -> bool:
        """O achado é redundante: outro alerta ativo de severidade igual ou maior já o explica."""
        return any(
            (g := self._gates.get(f"sinais.{c}")) is not None
            and g.active
            and SEVERITY_ORDER[g.sev] >= SEVERITY_ORDER[sev]
            for c in _REDUNDANT.get(code, ())
        )

    # ------------------------------------------------------------------ passo principal
    def update(self, sample: VitalSample) -> list[Finding]:
        t = sample.at
        if self.last_at is not None:
            gap = (t - self.last_at).total_seconds()
            if gap < self.min_step_s:
                return []
            if gap > 20 * 60:  # reconexão do monitor: janelas antigas não valem mais
                self._reset_windows()
        vals: dict[str, float | None] = {
            "hr": _num(sample.hr),
            "sbp": _num(sample.sbp),
            "dbp": _num(sample.dbp),
            "map": derived_map(sample),
            "rr": _num(sample.rr),
            "spo2": _num(sample.spo2),
            "temp_c": _num(sample.temp_c),
        }
        hr, sbp = vals["hr"], vals["sbp"]
        vals["si"] = hr / sbp if hr is not None and sbp not in (None, 0) else None
        self.news2_score = news2({k: v for k, v in vals.items() if v is not None})[0]
        vals["news2"] = float(self.news2_score)

        out: list[Finding] = []
        comps: dict[str, float] = {}
        if "limiar" in self.methods:
            out += self._limits(t, vals, comps)
        if "zscore" in self.methods:
            out += self._zscores(t, vals, comps)
        if "deriva" in self.methods:
            out += self._drift(t, vals, comps)
        if "iforest" in self.methods:
            out += self._iforest(t, vals, comps)
        self._push(t, vals)
        self.last_at = t
        self.n_samples += 1
        strong = sorted(comps.values(), reverse=True)
        top = strong[0] if strong else 0.0
        self.score = round(min(1.0, top + 0.1 * max(0, sum(c > 0.3 for c in strong) - 1)), 3)
        return out

    def _push(self, t: datetime, vals: dict[str, float | None]) -> None:
        """Atualiza janelas (após a avaliação: a amostra atual não entra na própria referência)."""
        for s in _SIG:
            x = vals[s]
            if x is None:
                continue
            w = self._win[s]
            w.append((t, x))
            while w and t - w[0][0] > self.window:
                w.popleft()
            e = self._ewma[s] = x if s not in self._ewma else 0.3 * x + 0.7 * self._ewma[s]
            r = self._ref[s]
            r.append((t, e))
            while r and t - r[0][0] > self.ref:
                r.popleft()

    # ------------------------------------------------------------------ (a)+(e) limites e derivados
    def _limits(
        self, t: datetime, vals: dict[str, float | None], comps: dict[str, float]
    ) -> list[Finding]:
        out: list[Finding] = []
        for lad in _LADDERS:
            x = vals.get(lad.sig)
            if x is None:
                self._gate(f"sinais.{lad.code}", None, False, t)
                continue
            sev: Severity | None = None
            for thr, s in lad.steps:  # do brando ao grave: o último degrau atingido vale
                if (x <= thr) if lad.dir < 0 else (x >= thr):
                    sev = s
            first = lad.steps[0][0]
            hold = x <= first + lad.margin if lad.dir < 0 else x >= first - lad.margin
            if sev:
                comps["limiar"] = max(comps.get("limiar", 0.0), 0.85 if sev == "critico" else 0.45)
            emit = self._gate(f"sinais.{lad.code}", sev, hold, t)
            if emit is None or self._covered(lad.code, emit):
                continue
            limit = next(thr for thr, s in lad.steps if s == emit)
            unit = f" {lad.unit}" if lad.unit else ""
            out.append(
                Finding(
                    code=f"sinais.{lad.code}",
                    title=f"{lad.title}: {x:.3g}{unit}",
                    description=(
                        f"{lad.title} ({x:.3g}{unit}) — limite de alerta "
                        f"{'≤' if lad.dir < 0 else '≥'} {limit:g}{unit}. Referência: {lad.ref}."
                    ),
                    severity=emit,
                    modality="sinais",
                    score=0.9 if emit == "critico" else 0.6,
                    at=t,
                    evidence={
                        "valor": round(x, 2),
                        "limite": limit,
                        "unidade": lad.unit,
                        "news2": self.news2_score,
                    },
                    recommendation=lad.rec,
                )
            )
        comps["limiar"] = max(comps.get("limiar", 0.0), min(1.0, self.news2_score / 10) * 0.9)
        si = vals.get("si")
        if si is not None:
            comps["limiar"] = max(
                comps.get("limiar", 0.0), min(1.0, max(0.0, (si - 0.7) / 0.5)) * 0.9
            )
        return out

    # ------------------------------------------------------------------ (b) z-score robusto
    def _zscores(
        self, t: datetime, vals: dict[str, float | None], comps: dict[str, float]
    ) -> list[Finding]:
        out: list[Finding] = []
        for s, cfg in _SIG.items():
            x, w = vals[s], self._win[s]
            code = f"sinais.mudanca_brusca_{s}"
            if x is None or len(w) < 12:
                self._gate(code, None, False, t)
                continue
            med, scale = _mad_scale([v for _, v in w], cfg.floor)
            z = (x - med) / scale
            adverse = z * cfg.abrupt if cfg.abrupt else abs(z)
            delta = abs(x - med)
            sev: Severity | None = None
            if adverse >= self.z_alert and delta >= cfg.min_change:
                sev = (
                    "critico"
                    if adverse >= 2 * self.z_alert and delta >= 2 * cfg.min_change
                    else "atencao"
                )
            # o escore só sobe se o desvio também tem tamanho clínico (z grande em sinal quase constante não vale)
            mag = min(1.0, delta / cfg.min_change)
            comps["zscore"] = max(
                comps.get("zscore", 0.0), min(1.0, max(0.0, adverse - 2) / 6) * 0.8 * mag
            )
            emit = self._gate(code, sev, sev is not None, t)
            if emit is None:
                continue
            sentido = "queda" if x < med else "alta"
            out.append(
                Finding(
                    code=code,
                    title=f"Mudança brusca de {cfg.label}: {sentido} de {delta:.3g} {cfg.unit}",
                    description=(
                        f"{cfg.label.capitalize()} saiu de ~{med:.3g} para {x:.3g} {cfg.unit} "
                        f"(z robusto {z:+.1f}, janela de {int(self.window.total_seconds() / 60)} min)."
                    ),
                    severity=emit,
                    modality="sinais",
                    score=round(min(1.0, abs(z) / (3 * self.z_alert)), 3),
                    at=t,
                    evidence={
                        "valor": round(x, 2),
                        "mediana_janela": round(med, 2),
                        "z_robusto": round(z, 2),
                        "variacao": round(x - med, 2),
                        "unidade": cfg.unit,
                    },
                    recommendation=_REC_ABRUPTA,
                )
            )
        return out

    # ------------------------------------------------------------------ (c) EWMA + CUSUM
    def _drift(
        self, t: datetime, vals: dict[str, float | None], comps: dict[str, float]
    ) -> list[Finding]:
        out: list[Finding] = []
        for s, cfg in _SIG.items():
            code = f"sinais.deriva_{s}"
            x, e = vals[s], self._ewma.get(s)
            old = [v for ts, v in self._ref[s] if t - ts >= self.lag]
            if x is None or e is None or len(old) < 20:
                self._gate(code, None, False, t)
                continue
            mu, sd = _mad_scale(old, cfg.floor)
            e = (
                0.3 * x + 0.7 * e
            )  # EWMA incluindo a amostra atual (a referência ainda não a inclui)
            z = (e - mu) / sd
            cs = self._cusum[s]
            cs[0] = max(0.0, cs[0] + z - self.k)  # deriva para cima
            cs[1] = max(0.0, cs[1] - z - self.k)  # deriva para baixo
            up, down = cs
            if cfg.drift > 0:
                stat, sentido = up, 1
            elif cfg.drift < 0:
                stat, sentido = down, -1
            else:
                stat, sentido = (up, 1) if up >= down else (down, -1)
            delta = e - mu
            ok = stat >= self.h and abs(delta) >= cfg.min_change and delta * sentido > 0
            # a gravidade clínica vem dos limites; a deriva só antecipa, por isso nunca passa de «atencao»
            sev: Severity | None = "atencao" if ok else None
            hold = stat >= self.h / 2 and abs(delta) >= cfg.min_change / 2 and delta * sentido > 0
            mag = min(1.0, abs(delta) / cfg.min_change) if delta * sentido > 0 else 0.0
            comps["deriva"] = max(
                comps.get("deriva", 0.0), min(1.0, stat / (2 * self.h)) * 0.8 * mag
            )
            emit = self._gate(code, sev, hold, t)
            if emit is None:
                continue
            out.append(
                Finding(
                    code=code,
                    title=f"Deriva de {cfg.label}: {'queda progressiva' if delta < 0 else 'aumento progressivo'}",
                    description=(
                        f"{cfg.label.capitalize()} se afastou da referência dos últimos "
                        f"{int(self.ref.total_seconds() / 60)} min ({mu:.3g} → {e:.3g} {cfg.unit}, "
                        f"CUSUM {stat:.1f} > {self.h:g}). Tendência sustentada, ainda sem cruzar necessariamente um limite."
                    ),
                    severity=emit,
                    modality="sinais",
                    score=round(min(1.0, stat / (3 * self.h)), 3),
                    at=t,
                    evidence={
                        "valor_suavizado": round(e, 2),
                        "referencia": round(mu, 2),
                        "variacao": round(delta, 2),
                        "cusum": round(stat, 2),
                        "limite_cusum": self.h,
                        "unidade": cfg.unit,
                    },
                    recommendation=_REC_DERIVA,
                )
            )
        return out

    # ------------------------------------------------------------------ (d) IsolationForest
    def _iforest(
        self, t: datetime, vals: dict[str, float | None], comps: dict[str, float]
    ) -> list[Finding]:
        cols = ("hr", "map", "rr", "spo2", "temp_c")
        if self._if is None:
            self._base_rows.append([vals[c] for c in cols])
            if len(self._base_rows) >= self.baseline_n:
                self._fit_iforest(cols)
            return []
        if not self._if_cols:
            return []
        # pré-condição clínica: ≥ 2 variáveis se afastando da linha de base no sentido adverso
        adverse = 0
        for c in self._if_cols:
            x = vals[c]
            if x is None:
                continue
            z = (x - self._if_med[c]) / self._if_sd[c]
            d = _SIG[c].drift
            adverse += (abs(z) if d == 0 else z * d) >= 2.0
        score = 0.0
        sev: Severity | None = None
        if adverse >= 2:
            row = [[vals[c] if vals[c] is not None else self._if_med[c] for c in self._if_cols]]
            score = float(-self._if.score_samples(row)[0])
            if score >= self.if_threshold:
                sev = "critico" if score >= self.if_threshold + 0.1 and adverse >= 3 else "atencao"
        comps["iforest"] = min(1.0, max(0.0, (score - 0.5) / 0.3)) * 0.8
        emit = self._gate("sinais.multivariada", sev, adverse >= 1, t)
        if emit is None:
            return []
        detail = {c: round(vals[c], 1) for c in self._if_cols if vals[c] is not None}
        return [
            Finding(
                code="sinais.multivariada",
                title="Combinação anômala de sinais vitais",
                description=(
                    f"{adverse} sinais se afastaram juntos da linha de base deste paciente ({detail}); "
                    f"IsolationForest: escore {score:.2f} (limite {self.if_threshold:g}). Cada valor pode estar "
                    "dentro do limite, mas a combinação é incomum para ele."
                ),
                severity=emit,
                modality="sinais",
                score=round(min(1.0, score), 3),
                at=t,
                evidence={
                    "escore_iforest": round(score, 3),
                    "limite": self.if_threshold,
                    "sinais_adversos": adverse,
                    **detail,
                },
                recommendation="Reavaliar o paciente: o padrão conjunto lembra deterioração (sepse, hipovolemia, insuficiência respiratória).",
            )
        ]

    def _fit_iforest(self, cols: tuple[str, ...]) -> None:
        from sklearn.ensemble import IsolationForest

        keep = [
            i
            for i in range(len(cols))
            if sum(r[i] is not None for r in self._base_rows) >= 0.8 * len(self._base_rows)
        ]
        if len(keep) < 3:  # sem sinais suficientes para um modelo multivariado
            self._if = False
            return
        self._if_cols = [cols[i] for i in keep]
        for i, c in zip(keep, self._if_cols, strict=True):
            col = [r[i] for r in self._base_rows if r[i] is not None]
            self._if_med[c], self._if_sd[c] = _mad_scale(col, _SIG[c].floor)
        x = [
            [r[i] if r[i] is not None else self._if_med[cols[i]] for i in keep]
            for r in self._base_rows
        ]
        self._if = IsolationForest(
            n_estimators=100, contamination="auto", random_state=self.random_state
        ).fit(x)


# ---------------------------------------------------------------------------
# Lote
# ---------------------------------------------------------------------------
def _sklearn_version() -> str | None:
    try:
        from importlib.metadata import version

        return version("scikit-learn")
    except Exception:  # pragma: no cover - metadado ausente
        return None


def detect_vital_anomalies(samples: list[VitalSample]) -> AnalysisResult:
    """Roda o detector online sobre a série inteira e consolida achados, série e métricas."""
    if not samples:
        return AnalysisResult(
            kind="sinais",
            summary="Sem amostras de sinais vitais para analisar.",
            warnings=["Série vazia"],
        ).finalize()
    ordered = sorted(samples, key=lambda s: s.at)
    det = OnlineVitalsDetector()
    findings: list[Finding] = []
    series: dict[str, list[Any]] = {
        k: []
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
            "anomaly_flag",
        )
    }
    marks: list[int] = []
    for i, s in enumerate(ordered):
        new = det.update(s)
        findings += new
        if new:
            marks.append(i)
        series["t"].append(s.at.isoformat())
        for k in ("hr", "sbp", "dbp", "rr", "spo2", "temp_c"):
            series[k].append(_num(getattr(s, k)))
        m = derived_map(s)
        series["map"].append(None if m is None else round(m, 1))
        series["anomaly_score"].append(det.score)
        series["anomaly_flag"].append(int(bool(det.active_codes)))
    series["anomaly_index"] = marks
    series["anomaly_at"] = [series["t"][i] for i in marks]

    hours = (ordered[-1].at - ordered[0].at).total_seconds() / 3600
    scores = series["anomaly_score"]
    tail = scores[-30:]
    n_crit = sum(f.severity == "critico" for f in findings)
    by_code: dict[str, int] = {}
    for f in findings:
        by_code[f.code] = by_code.get(f.code, 0) + 1
    worst = max(findings, key=lambda f: (SEVERITY_ORDER[f.severity], f.score), default=None)
    if findings:
        summary = (
            f"{len(findings)} {'alerta' if len(findings) == 1 else 'alertas'} em {hours:.1f} h de "
            f"monitorização ({n_crit} {'crítico' if n_crit == 1 else 'críticos'}). "
            f"Mais grave: {worst.title}. Escore atual {det.score:.2f}."
        )
    else:
        summary = f"Sem anomalias em {hours:.1f} h de monitorização; sinais dentro do esperado para o paciente."
    warnings = []
    if len(ordered) < 60:
        warnings.append(
            "Série curta (< 60 amostras): z-score, deriva e IsolationForest têm pouca referência."
        )
    for k, label in (("hr", "FC"), ("map", "PAM"), ("spo2", "SpO2")):
        if not any(v is not None for v in series[k]):
            warnings.append(f"Sem {label} na série: regras dependentes dela não foram aplicadas.")
    models = [
        ModelInfo(
            name="Limiares fisiológicos + NEWS2 + índice de choque",
            task="detecção de anomalias",
            provider="regra",
            details={"referencias": "NEWS2 (RCP/NHS), qSOFA (Sepsis-3), PROT-008"},
        ),
        ModelInfo(
            name="Z-score robusto (mediana/MAD)",
            task="mudança brusca",
            provider="regra",
            details={"janela_min": 30, "z_alerta": det.z_alert},
        ),
        ModelInfo(
            name="EWMA + CUSUM bilateral",
            task="deriva/tendência",
            provider="regra",
            details={"lambda": 0.3, "k": det.k, "h": det.h, "referencia_min": 90},
        ),
        ModelInfo(
            name="IsolationForest (scikit-learn)",
            task="anomalia multivariada",
            provider="local",
            version=_sklearn_version(),
            details={
                "n_estimators": 100,
                "linha_de_base_amostras": det.baseline_n,
                "limite_escore": det.if_threshold,
            },
        ),
    ]
    return AnalysisResult(
        kind="sinais",
        summary=summary,
        risk_score=round(max(tail), 3),
        findings=findings,
        metrics={
            "amostras": len(ordered),
            "duracao_h": round(hours, 2),
            "alertas": len(findings),
            "alertas_criticos": n_crit,
            "alertas_por_hora": round(len(findings) / hours, 2) if hours > 0 else None,
            "alertas_por_codigo": by_code,
            "escore_maximo": max(scores),
            "escore_final": det.score,
            "news2_final": det.news2_score,
            "primeiro_alerta": findings[0].at.isoformat() if findings and findings[0].at else None,
        },
        series=series,
        models=models,
        duration_s=(ordered[-1].at - ordered[0].at).total_seconds(),
        warnings=warnings,
    ).finalize()
