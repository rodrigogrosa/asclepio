"""Acústica (Praat) e indicadores vocais em sinais sintéticos: sem rede, sem modelos."""

from __future__ import annotations

import numpy as np
import parselmouth
import pytest
from asclepio_multimodal.audio.features import extract_features
from asclepio_multimodal.audio.vocal import (
    SPEECH,
    indicator_findings,
    score_indicators,
    voice_quality_score,
)

SR = 16_000


def voiced(seconds: float, f0: float = 120.0, jitter: float = 0.0, seed: int = 0) -> np.ndarray:
    """Trem de ciclos com 12 harmônicos (1/k); ``jitter`` = desvio relativo de cada período."""
    rng = np.random.default_rng(seed)
    periods = (1 / f0) * (1 + jitter * rng.standard_normal(int(seconds * f0 * 1.3) + 10))
    edges = np.cumsum(periods)
    t = np.arange(int(seconds * SR)) / SR
    i = np.searchsorted(edges, t, side="right")
    tau = (t - (edges[i] - periods[i])) / periods[i]
    return sum(np.sin(2 * np.pi * k * tau) / k for k in range(1, 13)) / 3


def syllables(x: np.ndarray, rate_hz: float = 4.0) -> np.ndarray:
    """Envelope de ~30 dB de profundidade a ``rate_hz`` sílabas por segundo."""
    t = np.arange(len(x)) / SR
    return x * (0.03 + 0.97 * np.sin(np.pi * rate_hz * t) ** 2)


def sound(x: np.ndarray) -> parselmouth.Sound:
    return parselmouth.Sound(x.astype(float) * 0.5, sampling_frequency=SR)


def test_f0_jitter_hnr():
    clean = extract_features(sound(voiced(2.0))).features
    shaky = extract_features(sound(voiced(2.0, jitter=0.02))).features
    noisy = extract_features(
        sound(voiced(2.0) + 0.5 * np.random.default_rng(1).standard_normal(2 * SR))
    ).features
    assert clean["f0_mean_hz"] == pytest.approx(120, abs=3)
    assert clean["jitter_local_pct"] < 0.5
    assert (
        shaky["jitter_local_pct"] > 1.0
        and shaky["jitter_local_pct"] > 3 * clean["jitter_local_pct"]
    )
    assert clean["hnr_db"] > 20
    assert noisy["hnr_db"] < clean["hnr_db"] - 8
    assert clean["f0_sd_st"] < 0.5  # tom constante: quase nenhuma variação


def test_pausas_e_silabas():
    gap = np.zeros(int(0.15 * SR))  # lacuna < 250 ms não é pausa
    parts = [
        np.zeros(SR // 2),  # silêncio inicial não conta
        syllables(voiced(1.0)),
        gap,
        syllables(voiced(1.0)),
        np.zeros(SR),  # pausa de 1,0 s
        syllables(voiced(2.0)),
        np.zeros(int(0.4 * SR)),  # pausa de 0,4 s
        syllables(voiced(1.5)),
        np.zeros(SR // 2),  # silêncio final não conta
    ]
    x = np.concatenate(parts)
    x = x + 1e-5 * np.random.default_rng(2).standard_normal(len(x))
    ac = extract_features(sound(x))
    f = ac.features
    assert f["n_pauses"] == 2
    assert f["pause_total_s"] == pytest.approx(1.4, abs=0.12)
    assert f["pause_mean_s"] == pytest.approx(0.7, abs=0.08)
    assert f["n_breath_groups"] == 3
    assert f["articulation_rate"] == pytest.approx(4.0, abs=1.0)  # 4 sílabas/s inseridas
    assert len(ac.series["t"]) == len(ac.series["f0"]) == len(ac.series["intensity"])
    assert all(a < b for a, b in ac.pauses)


def test_indicadores_na_referencia_e_fora_dela():
    typical = {k: r.median for k, r in SPEECH.items()}
    inds = score_indicators(typical, resp_events_per_min=0.0)
    assert all(i["score"] == 0 and i["level"] == "normal" for i in inds.values())
    assert indicator_findings(inds) == []

    # voz monótona, fala lenta e pausas longas → fadiga; frases curtas e chiado → respiratório
    tired = {**typical, "f0_sd_st": 0.5, "articulation_rate": 3.0, "pause_mean_s": 1.2}
    breathless = {**typical, "breath_group_mean_s": 1.0, "pauses_per_min": 25}
    f = {x.code: x for x in indicator_findings(score_indicators(tired, 0.0))}
    assert f["audio.fadiga"].severity in ("atencao", "critico")
    assert "não é diagnóstico" in f["audio.fadiga"].description
    g = {x.code for x in indicator_findings(score_indicators(breathless, 4.0))}
    assert "audio.dificuldade_respiratoria" in g
    assert score_indicators({"hnr_db": 20.0}, None)["fadiga"]["score"] is None  # medidas de menos


def test_qualidade_vocal_de_vogal_separa_o_voz_ruim():
    good = {"jitter_local_pct": 0.3, "shimmer_local_pct": 3.5, "hnr_db": 20.0}
    bad = {"jitter_local_pct": 1.5, "shimmer_local_pct": 9.0, "hnr_db": 9.0}
    assert voice_quality_score(good) < 0.1 < 0.6 < voice_quality_score(bad)


def test_silencio_e_ruido_nao_quebram():
    mudo = extract_features(sound(np.zeros(3 * SR))).features
    assert mudo["f0_mean_hz"] is None and mudo["n_pauses"] == 0
    ruido = extract_features(sound(np.random.default_rng(0).standard_normal(3 * SR) * 0.1)).features
    assert ruido["f0_mean_hz"] is None and ruido["jitter_local_pct"] is None
