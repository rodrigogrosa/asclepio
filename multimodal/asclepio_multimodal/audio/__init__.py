"""Análise de áudio de consultas: Azure Speech to Text, Azure Text Analytics e acústica da voz.

Importar este pacote é barato; os módulos pesados (Praat, Whisper, AST) só carregam em
``analyze_audio``.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from ..schemas import AnalysisResult


def analyze_audio(
    path: Path,
    out_dir: Path,
    *,
    language: str | None = None,
    progress: Callable[[float, str], None] | None = None,
) -> AnalysisResult:
    """Analisa um áudio de consulta (WAV, MP3, M4A, OGG, WEBM…) e grava os artefatos em ``out_dir``.

    Devolve ``AnalysisResult(kind="audio")``; ``progress(fração 0..1, mensagem)`` é opcional.
    Levanta ``MediaError`` se o arquivo não for áudio decodificável ou tiver menos de 1 s.
    """
    from .pipeline import run

    return run(Path(path), Path(out_dir), language, progress)


__all__ = ["analyze_audio"]
