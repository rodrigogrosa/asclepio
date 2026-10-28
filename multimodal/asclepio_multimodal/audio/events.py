"""Eventos sonoros de interesse clínico (tosse, respiração, chiado…) com o AST do AudioSet.

O Audio Spectrogram Transformer (Gong et al., 2021) treinado no AudioSet tem as classes Cough,
Throat clearing, Sneeze, Breathing, Wheeze, Gasp, Sigh e Pant. Passamos janelas de 1 s (salto de
0,5 s); a probabilidade (sigmoide) de cada grupo de classes vira evento quando passa do limiar e
janelas vizinhas do mesmo tipo se fundem em um intervalo.
"""

from __future__ import annotations

from collections.abc import Callable
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from ..config import get_settings
from ..schemas import Finding

# tipo → (classes do AudioSet, nome em português)
EVENT_TYPES: dict[str, tuple[list[str], str]] = {
    "tosse": (["Cough"], "tosse"),
    "pigarro": (["Throat clearing"], "pigarro"),
    "espirro": (["Sneeze"], "espirro"),
    "respiracao": (["Breathing", "Pant"], "respiração audível"),
    "chiado": (["Wheeze"], "chiado"),
    "suspiro": (["Sigh"], "suspiro"),
    "engasgo": (["Gasp"], "engasgo/gasp"),
}
# As sigmoides do AudioSet raramente passam de 0,5, então o limiar é por tipo. Tosse, respiração e
# espirro: melhor F1 na metade A do ESC-50, com piso para ficar ≤ 0,3 evento/min em fala sadia
# (FLEURS) — espirro sobe de 0,03 para 0,1 por isso. Pigarro, suspiro e engasgo não têm classe no
# ESC-50: limiares que mantêm ≤ 0,3 evento/min no FLEURS; chiado usa o padrão. NÃO validados.
# Números em audio_eval.json (esc50, normas_fala).
DEFAULT_THRESHOLD = 0.15
THRESHOLDS: dict[str, float] = {
    "tosse": 0.08,
    "respiracao": 0.03,
    "espirro": 0.1,
    "pigarro": 0.3,
    "suspiro": 0.2,
    "engasgo": 0.5,
}
WINDOW_S, HOP_S = 1.0, 0.5
SILENT_RMS = 1e-3  # janela praticamente muda: nem passa pelo modelo


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


@lru_cache(maxsize=1)
def _load(model: str, device: str):
    from transformers import ASTFeatureExtractor, ASTForAudioClassification

    fe = ASTFeatureExtractor.from_pretrained(model)
    net = ASTForAudioClassification.from_pretrained(model).to(device).eval()
    idx = {n: i for i, n in net.config.id2label.items()}
    groups = {k: [int(idx[n]) for n in names] for k, (names, _) in EVENT_TYPES.items()}
    return fe, net, groups


def window_probabilities(
    audio: np.ndarray,
    sr: int,
    *,
    window_s: float = WINDOW_S,
    hop_s: float = HOP_S,
    batch: int = 8,
    progress: Callable[[float], None] | None = None,
) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Probabilidade por janela e tipo. Devolve (inícios em s, matriz janelas×tipos, tipos)."""
    import torch

    cfg = get_settings()
    dev = _device()
    fe, net, groups = _load(cfg.audio_events_model, dev)
    win, hop = int(window_s * sr), int(hop_s * sr)
    n = max(1, 1 + (len(audio) - win + hop - 1) // hop) if len(audio) > win else 1
    starts = np.arange(n) * hop
    types = list(groups)
    probs = np.zeros((n, len(types)), dtype=np.float32)
    live = [
        i for i, s in enumerate(starts) if np.sqrt(np.mean(audio[s : s + win] ** 2)) >= SILENT_RMS
    ]
    for b in range(0, len(live), batch):
        idx = live[b : b + batch]
        clips = [audio[starts[i] : starts[i] + win] for i in idx]
        inputs = fe(clips, sampling_rate=sr, return_tensors="pt").to(dev)
        with torch.inference_mode():
            p = net(**inputs).logits.sigmoid().cpu().numpy()
        for row, i in zip(p, idx, strict=True):
            probs[i] = [row[groups[t]].max() for t in types]
        if progress:
            progress(min(1.0, (b + batch) / len(live)))
    return starts / sr, probs, types


def merge_windows(
    starts: np.ndarray,
    probs: np.ndarray,
    types: list[str],
    window_s: float = WINDOW_S,
    thresholds: dict[str, float] | None = None,
) -> list[dict[str, Any]]:
    """Janelas consecutivas acima do limiar, do mesmo tipo, viram um intervalo."""
    th = {
        **dict.fromkeys(types, DEFAULT_THRESHOLD),
        **(THRESHOLDS if thresholds is None else thresholds),
    }
    events: list[dict[str, Any]] = []
    for j, t in enumerate(types):
        last: dict[str, Any] | None = None
        for i in np.flatnonzero(probs[:, j] >= th[t]):
            s, p = float(starts[i]), float(probs[i, j])
            if last and s <= last["end"]:
                last["end"] = round(s + window_s, 2)
                last["score"] = max(last["score"], p)
            else:
                last = {
                    "type": t,
                    "label": EVENT_TYPES[t][1],
                    "start": round(s, 2),
                    "end": round(s + window_s, 2),
                    "score": p,
                }
                events.append(last)
    for e in events:
        e["score"] = round(e["score"], 3)
    return sorted(events, key=lambda e: e["start"])


def detect_events(wav: Path, progress: Callable[[float], None] | None = None) -> dict[str, Any]:
    """Eventos sonoros do WAV 16 kHz mono: lista de intervalos, contagens e taxa por minuto."""
    import soundfile as sf

    audio, sr = sf.read(str(wav), dtype="float32")
    starts, probs, types = window_probabilities(audio, sr, progress=progress)
    events = merge_windows(starts, probs, types)
    minutes = max(len(audio) / sr / 60, 1e-6)
    counts = {t: sum(1 for e in events if e["type"] == t) for t in types}
    return {
        "events": events,
        "counts": counts,
        "per_min": {t: round(c / minutes, 2) for t, c in counts.items()},
        "model": get_settings().audio_events_model,
        "window_s": WINDOW_S,
        "hop_s": HOP_S,
        "thresholds": {t: THRESHOLDS.get(t, DEFAULT_THRESHOLD) for t in types},
    }


# tipo → (mínimo de ocorrências, severidade, título, o que significa)
_RULES: dict[str, tuple[int, str, str, str]] = {
    "tosse": (3, "atencao", "Tosse frequente", "Tosse repetida durante a consulta."),
    "chiado": (1, "atencao", "Chiado audível", "Som sibilante compatível com chiado no peito."),
    "respiracao": (3, "atencao", "Respiração audível", "Respiração ruidosa ou ofegante ao falar."),
    "engasgo": (
        3,
        "atencao",
        "Engasgos/inspirações bruscas",
        "Inspirações súbitas durante a fala.",
    ),
}


def event_findings(det: dict[str, Any]) -> list[Finding]:
    out = []
    for t, (min_n, sev, title, why) in _RULES.items():
        evs = [e for e in det["events"] if e["type"] == t]
        if len(evs) < min_n:
            continue
        top = max(e["score"] for e in evs)
        out.append(
            Finding(
                code=f"audio.{t}",
                title=title,
                description=f"{why} {len(evs)} ocorrência(s) detectada(s) pelo modelo AudioSet.",
                severity=sev,  # type: ignore[arg-type]
                modality="audio",
                score=round(min(1.0, 0.5 * top + 0.5 * min(1.0, len(evs) / 6)), 2),
                t_start=evs[0]["start"],
                t_end=evs[-1]["end"],
                evidence={
                    "ocorrencias": len(evs),
                    "por_minuto": det["per_min"][t],
                    "prob_max": top,
                },
                recommendation="Avaliar sintomas respiratórios e ausculta pulmonar.",
            )
        )
    return out
