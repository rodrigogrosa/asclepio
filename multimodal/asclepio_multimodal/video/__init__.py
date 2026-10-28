"""Análise de vídeo clínico: OpenPose (postura) + YOLOv8 (pessoas, objetos, áreas críticas)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..schemas import AnalysisResult

__all__ = ["analyze_video"]


def analyze_video(
    path: Path,
    out_dir: Path,
    profile: str = "fisioterapia",
    *,
    exercise: str | None = "agachamento",
    zones: dict | None = None,
    sample_fps: float | None = None,
    progress: Callable[[float, str], None] | None = None,
    regiao: tuple[float, float, float, float] | None = None,
) -> AnalysisResult:
    """Analisa um vídeo e devolve um ``AnalysisResult(kind="video")``.

    Perfis: ``fisioterapia`` (com ``exercise`` em ``rules.PROTOCOLOS``), ``quarto`` (queda,
    imobilidade, agitação, saída do leito) e ``cirurgia`` (lotação, objetos e entradas na área
    crítica). ``zones`` mapeia o nome da zona a um polígono de vértices normalizados (0..1) e
    substitui a zona padrão do perfil (``leito``/``chao`` no quarto, ``area_esteril`` na cirurgia).
    ``regiao`` (x0, y0, x1, y1 normalizados) recorta o quadro antes da análise — por exemplo, os
    vídeos do UR Fall Detection trazem a profundidade à esquerda e o RGB à direita (0.5, 0, 1, 1).
    ``progress(fracao, etapa)`` é chamado ao longo do processamento.

    Grava em ``out_dir``: ``report.md``, ``anotado.mp4``, ``grafico_*.png`` e um JPEG por achado
    (nomes em ``artifacts``). Levanta ``media.MediaError`` se o vídeo for ilegível.
    """
    from .pipeline import analyze_video as _analisar

    return _analisar(
        path, out_dir, profile, exercise=exercise, zones=zones, sample_fps=sample_fps,
        progress=progress, regiao=regiao,
    )  # fmt: skip
