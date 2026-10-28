"""Leitura de quadros do vídeo: amostragem por tempo e releitura por índice (para o relatório)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from pathlib import Path

import cv2
import numpy as np

from ..media import MediaError

Regiao = tuple[float, float, float, float]  # x0, y0, x1, y1 normalizados


def abrir(path: Path) -> tuple[cv2.VideoCapture, float, int]:
    """Abre o vídeo e devolve (captura, fps, nº de quadros). ``MediaError`` se ilegível."""
    cap = cv2.VideoCapture(str(path))
    if not path.exists() or not cap.isOpened():
        raise MediaError(
            "Não foi possível abrir este vídeo. Envie MP4, MOV, AVI, MKV ou WEBM com a imagem "
            "intacta (o arquivo pode estar corrompido ou usar um codec não suportado)."
        )
    fps = cap.get(cv2.CAP_PROP_FPS)
    if not 1 <= fps <= 240:
        fps = 30.0  # metadado ausente/absurdo: assume 30 quadros/s
    return cap, float(fps), int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)


def recortar(frame: np.ndarray, regiao: Regiao | None) -> np.ndarray:
    if regiao is None:
        return frame
    h, w = frame.shape[:2]
    x0, y0, x1, y1 = regiao
    return frame[int(y0 * h) : int(y1 * h), int(x0 * w) : int(x1 * w)]


def amostrar(
    cap: cv2.VideoCapture, fps: float, sample_fps: float, max_s: float, regiao: Regiao | None
) -> Iterator[tuple[int, float, np.ndarray]]:
    """Gera (índice, tempo s, quadro) a cada ``1/sample_fps`` s, até ``max_s``."""
    passo = fps / sample_fps
    k, i = 0, 0
    while True:
        alvo = round(k * passo)
        if alvo / fps > max_s:
            return
        while i < alvo:
            if not cap.grab():
                return
            i += 1
        ok, frame = cap.read()  # grab + decodificação do quadro `alvo`
        if not ok:
            return
        i += 1
        yield alvo, alvo / fps, recortar(frame, regiao)
        k += 1


def reler(
    path: Path, indices: Iterable[int], regiao: Regiao | None
) -> Iterator[tuple[int, np.ndarray]]:
    """Relê, em ordem, apenas os quadros ``indices`` (crescentes)."""
    cap = cv2.VideoCapture(str(path))
    alvos, i = sorted(set(indices)), 0
    try:
        for alvo in alvos:
            while i < alvo:
                if not cap.grab():
                    return
                i += 1
            ok, frame = cap.read()
            if not ok:
                return
            i += 1
            yield alvo, recortar(frame, regiao)
    finally:
        cap.release()
