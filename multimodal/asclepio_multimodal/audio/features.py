"""Acústica da voz e da fala com o Praat (parselmouth).

Medidas clássicas de qualidade vocal (F0, jitter, shimmer, HNR), de prosódia (intensidade,
pausas, taxa de articulação) e de respiração (grupos de fala entre pausas). Os núcleos
silábicos seguem de Jong & Wempe (2009, *Behavior Research Methods* 41:385): picos de
intensidade acima de (percentil 99 − 25 dB), com queda de ≥ 2 dB entre picos, em trecho vozeado.
Pausa = silêncio ≥ 250 ms (Goldman-Eisler, 1968).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

MIN_PAUSE_S = 0.25
SILENCE_DB = 25.0  # abaixo do percentil 99 da intensidade = silêncio (de Jong & Wempe)
MIN_DIP_DB = 2.0
FULL_SCALE_DB = 93.98  # 20·log10(1 / 2e-5): intensidade do Praat → dB re amplitude 1,0 (dBFS)
SERIES_STEP = 5  # a série para gráfico guarda 1 a cada 5 quadros de 10 ms (20 pontos/s)


@dataclass
class Acoustics:
    features: dict[str, float | None]
    series: dict[str, list[Any]]
    pauses: list[tuple[float, float]] = field(default_factory=list)
    groups: list[tuple[float, float]] = field(default_factory=list)  # grupos respiratórios
    nuclei: list[float] = field(default_factory=list)  # instantes dos núcleos silábicos


def load_sound(path: Path):
    import parselmouth

    return parselmouth.Sound(str(path))


def _num(x: float) -> float | None:
    return None if x is None or not math.isfinite(x) or x <= -199 else float(x)


def _perturbation(snd, f0_floor: float, f0_ceiling: float) -> dict[str, float | None]:
    """Jitter e shimmer locais (%) pelo ponto-processo periódico; ``None`` se faltar período."""
    from parselmouth.praat import call

    out: dict[str, float | None] = {"jitter_local_pct": None, "shimmer_local_pct": None}
    try:
        pp = call(snd, "To PointProcess (periodic, cc)", f0_floor, f0_ceiling)
        out["jitter_local_pct"] = _num(
            100 * call(pp, "Get jitter (local)", 0, 0, 0.0001, 0.02, 1.3)
        )
        out["shimmer_local_pct"] = _num(
            100 * call([snd, pp], "Get shimmer (local)", 0, 0, 0.0001, 0.02, 1.3, 1.6)
        )
    except Exception:  # Praat recusa trechos sem períodos suficientes: a medida fica ausente
        pass
    return out


def _silent_runs(speech: np.ndarray, step: float) -> list[tuple[float, float]]:
    """Intervalos (s) de quadros não-fala, em índices de quadro → segundos."""
    runs, start = [], None
    for i, v in enumerate(speech):
        if not v and start is None:
            start = i
        elif v and start is not None:
            runs.append((start * step, i * step))
            start = None
    if start is not None:
        runs.append((start * step, len(speech) * step))
    return runs


def extract_features(snd, *, f0_floor: float = 75.0, f0_ceiling: float = 500.0) -> Acoustics:
    """Mede a voz e a fala de um ``parselmouth.Sound`` (qualquer taxa; vogal ou fala corrente)."""
    from parselmouth.praat import call
    from scipy.signal import argrelmax

    if snd.n_channels > 1:
        snd = snd.convert_to_mono()
    step = 0.01
    dur = float(snd.duration)

    pitch = snd.to_pitch(time_step=step, pitch_floor=f0_floor, pitch_ceiling=f0_ceiling)
    f0 = pitch.selected_array["frequency"]
    voiced = f0 > 0
    # janela de 32 ms (min. 100 Hz): suaviza menos que a de 64 ms do script original e separa
    # melhor as sílabas do português (núcleos ÷ grupos vocálicos do texto, em 110 falas do FLEURS: 0,53 → 0,89)
    inten = snd.to_intensity(minimum_pitch=100, time_step=step)
    db = np.asarray(inten.values[0], dtype=float)
    # Pitch e intensidade têm quadros ligeiramente diferentes; alinhamos pelo menor
    n = min(len(f0), len(db))
    f0, voiced, db = f0[:n], voiced[:n], db[:n]
    t = np.arange(n) * step + inten.xmin

    feats: dict[str, float | None] = {"duration_s": round(dur, 3)}
    st = 12 * np.log2(f0[voiced]) if voiced.sum() >= 5 else np.array([])
    feats["f0_mean_hz"] = float(f0[voiced].mean()) if st.size else None
    feats["f0_sd_hz"] = float(f0[voiced].std()) if st.size else None
    feats["f0_sd_st"] = float(st.std()) if st.size else None
    feats["f0_range_st"] = float(np.percentile(st, 95) - np.percentile(st, 5)) if st.size else None
    feats["voiced_fraction"] = float(voiced.mean()) if n else None
    feats.update(_perturbation(snd, f0_floor, f0_ceiling))
    try:
        feats["hnr_db"] = _num(
            call(snd.to_harmonicity_cc(time_step=step, minimum_pitch=f0_floor), "Get mean", 0, 0)
        )
    except Exception:
        feats["hnr_db"] = None

    # --- fala: silêncio, pausas e grupos respiratórios ---
    q99 = float(np.percentile(db, 99)) if n else 0.0
    # shortcut: limiar fixo (p99 − 25 dB); ruído de fundo alto esconde pausas — estimar o piso de ruído se for preciso
    thr = q99 - SILENCE_DB
    speech = db >= thr
    pauses: list[tuple[float, float]] = []
    groups: list[tuple[float, float]] = []
    nuclei: list[float] = []
    if speech.any():
        first, last = int(np.argmax(speech)), n - int(np.argmax(speech[::-1]))
        span = (last - first) * step
        runs = [(a, b) for a, b in _silent_runs(speech[first:last], step) if b - a >= MIN_PAUSE_S]
        pauses = [(round(a + first * step, 3), round(b + first * step, 3)) for a, b in runs]
        edges = [first * step] + [x for p in pauses for x in p] + [last * step]
        groups = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
        pause_total = sum(b - a for a, b in pauses)
        phon_time = max(span - pause_total, 1e-6)
        cand = [int(i) for i in argrelmax(db)[0] if db[i] >= thr]
        nuclei = [
            float(t[p])
            for prev, p in zip([None, *cand], cand, strict=False)
            if voiced[p] and (prev is None or db[p] - db[prev : p + 1].min() >= MIN_DIP_DB)
        ]
        sp = speech & (np.arange(n) >= first) & (np.arange(n) < last)
        iv = np.diff(nuclei)
        iv = iv[iv < 0.5]  # só intervalos dentro da mesma frase
        slope = np.polyfit(t[sp], db[sp], 1)[0] * 60 if sp.sum() > 20 else None
        feats.update(
            speech_span_s=round(span, 3),
            n_pauses=len(pauses),
            pause_total_s=round(pause_total, 3),
            pause_mean_s=round(pause_total / len(pauses), 3) if pauses else 0.0,
            pause_ratio=round(pause_total / span, 4) if span > 0 else 0.0,
            pauses_per_min=round(len(pauses) / (span / 60), 2) if span > 0 else 0.0,
            n_syllables=len(nuclei),
            syllable_interval_cv=round(float(iv.std() / iv.mean()), 3) if len(iv) >= 5 else None,
            speech_rate=round(len(nuclei) / span, 3) if span > 0 else None,
            articulation_rate=round(len(nuclei) / phon_time, 3),
            phonation_ratio=round(float(voiced[first:last].sum() * step / span), 4),
            breath_group_mean_s=round(float(np.mean([b - a for a, b in groups])), 3),
            n_breath_groups=len(groups),
            intensity_mean_db=round(float(db[sp].mean()), 2),
            intensity_sd_db=round(float(db[sp].std()), 2),
            level_dbfs=round(float(db[sp].mean()) - FULL_SCALE_DB, 2),
            intensity_slope_db_min=round(float(slope), 2) if slope is not None else None,
        )
    series = {
        "t": [round(float(x), 2) for x in t[::SERIES_STEP]],
        "f0": [
            round(float(v), 1) if ok else None
            for v, ok in zip(f0[::SERIES_STEP], voiced[::SERIES_STEP], strict=True)
        ],
        "intensity": [round(float(max(v, thr - 20)), 1) for v in db[::SERIES_STEP]],
    }
    return Acoustics(feats, series, pauses, groups, nuclei)
