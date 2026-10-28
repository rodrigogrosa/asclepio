"""Plano B local: transcrição com Whisper (Hugging Face) e sentimento por léxico.

Entra quando o Azure Speech / Language não está configurado ou falha. O Whisper roda no
``mps`` do Mac quando existe, senão na CPU; os pesos ficam em ``data/models/hf`` (HF_HOME).
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from ..config import get_settings
from .critical_terms import fold

_SENTENCE_END = re.compile(r"[.!?…]$")


def _device() -> str:
    import torch

    return "mps" if torch.backends.mps.is_available() else "cpu"


@lru_cache(maxsize=2)
def _pipeline(model: str, device: str):
    from transformers import pipeline

    return pipeline("automatic-speech-recognition", model=model, device=device)


def _language_name(code: str) -> str:
    from transformers.models.whisper.tokenization_whisper import LANGUAGES

    return LANGUAGES.get(code.split("-")[0].lower(), "portuguese")


def segments_from_words(words: list[dict[str, Any]], max_gap: float = 1.0) -> list[dict[str, Any]]:
    """Agrupa palavras em frases: fecha no ponto final ou numa pausa > ``max_gap`` s."""
    segs: list[dict[str, Any]] = []
    cur: list[dict[str, Any]] = []
    for i, w in enumerate(words):
        cur.append(w)
        nxt = words[i + 1] if i + 1 < len(words) else None
        if nxt is None or _SENTENCE_END.search(w["word"]) or nxt["start"] - w["end"] > max_gap:
            segs.append(
                {
                    "text": " ".join(x["word"] for x in cur),
                    "start": cur[0]["start"],
                    "end": cur[-1]["end"],
                    "confidence": None,
                }
            )
            cur = []
    return segs


def transcribe_local(wav: Path, language: str = "pt-BR") -> dict[str, Any]:
    """Transcrição com palavras e instantes. ``wav``: WAV 16 kHz mono (saída de ``to_wav``)."""
    import soundfile as sf

    model = get_settings().whisper_model
    audio, sr = sf.read(str(wav), dtype="float32")
    pipe = _pipeline(model, _device())
    out = pipe(
        {"raw": audio, "sampling_rate": sr},
        return_timestamps="word",
        chunk_length_s=30,
        ignore_warning=True,
        generate_kwargs={"language": _language_name(language), "task": "transcribe"},
    )
    words = []
    for ch in out.get("chunks", []):
        a, b = ch["timestamp"]
        w = ch["text"].strip()
        if w:
            words.append(
                {
                    "word": w,
                    "start": round(float(a or 0.0), 2),
                    "end": round(float(b if b is not None else (a or 0.0)), 2),
                    "confidence": None,  # o Whisper não expõe confiança por palavra
                }
            )
    return {
        "text": out["text"].strip(),
        "segments": segments_from_words(words),
        "words": words,
        "model": model,
    }


# --------------------------------------------------------------------------- sentimento local
# Léxico pequeno e transparente (relato de saúde em pt-BR). Não substitui o Azure: serve para a
# tela nunca ficar sem sentimento. Pesos: ±1 comum, ±2 forte.
_NEG = {
    "dor": 1,
    "dores": 1,
    "medo": 2,
    "assustad": 2,
    "preocupad": 1,
    "ansios": 2,
    "ansiedade": 2,
    "angustia": 2,
    "desesper": 2,
    "triste": 1,
    "tristeza": 1,
    "pior": 2,
    "piorando": 2,
    "piorou": 2,
    "mal": 1,
    "ruim": 1,
    "terrivel": 2,
    "insuportavel": 2,
    "cansad": 1,
    "cansaco": 1,
    "fraqueza": 1,
    "sem energia": 2,
    "nao consigo": 2,
    "falta de ar": 2,
    "sufoc": 2,
    "incomod": 1,
    "febre": 1,
    "tontura": 1,
    "nao aguento": 2,
    "chorando": 2,
    "sozinh": 1,
    "desanimad": 2,
    "chiado": 1,
}
_POS = {
    "melhor": 1,
    "melhorou": 2,
    "melhorando": 2,
    "bem": 1,
    "otimo": 2,
    "tranquil": 1,
    "aliviad": 2,
    "obrigad": 1,
    "feliz": 2,
    "contente": 1,
    "disposto": 1,
    "disposicao": 1,
    "normal": 1,
    "sem dor": 2,
    "dormindo bem": 2,
    "durmo bem": 2,
    "animad": 2,
    "confiante": 1,
}
_NEGATORS = ("nao ", "nunca ", "nego ", "sem ")


def _score(sentence: str) -> tuple[float, float]:
    s = " " + fold(sentence) + " "
    pos = neg = 0.0
    for lex, bucket in ((_POS, "pos"), (_NEG, "neg")):
        for term, w in lex.items():
            for m in re.finditer(r"(?<=\W)" + re.escape(term), s):
                before = s[max(0, m.start() - 12) : m.start()]
                flip = term not in ("nao consigo", "nao aguento", "sem energia", "sem dor") and any(
                    n in before for n in _NEGATORS
                )
                good = (bucket == "pos") != flip
                if good:
                    pos += w
                else:
                    neg += w
    return pos, neg


def sentiment_local(text: str) -> dict[str, Any]:
    """Sentimento por frase e geral no mesmo formato do Azure (``scores`` somam 1)."""
    from .azure_text import split_sentences

    sents = []
    tp = tn = 0.0
    for off, sent in split_sentences(text):
        pos, neg = _score(sent)
        tp, tn = tp + pos, tn + neg
        sents.append(
            {"text": sent, "offset": off, "sentiment": _label(pos, neg), "scores": _probs(pos, neg)}
        )
    return {"overall": _label(tp, tn), "scores": _probs(tp, tn), "sentences": sents}


def _label(pos: float, neg: float) -> str:
    if pos and neg and min(pos, neg) / max(pos, neg) > 0.6:
        return "mixed"
    if neg > pos:
        return "negative"
    return "positive" if pos > neg else "neutral"


def _probs(pos: float, neg: float) -> dict[str, float]:
    neutral = 1.0
    total = pos + neg + neutral
    return {
        "positive": round(pos / total, 3),
        "neutral": round(neutral / total, 3),
        "negative": round(neg / total, 3),
    }
