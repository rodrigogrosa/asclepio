"""Detecção de pessoas e objetos (YOLOv8, COCO) e geometria de áreas críticas."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Protocol

import numpy as np

from ..config import get_settings
from .pose import Caixa, Pose, _caminho_yolo, threads_opencv


class Deteccao(NamedTuple):
    rotulo: str  # nome COCO em inglês ('person', 'cell phone'…)
    conf: float
    caixa: Caixa


@dataclass
class Amostra:
    """Um quadro amostrado: tudo o que as redes enxergaram nele."""

    t: float  # s desde o início do vídeo
    idx: int  # índice do quadro no arquivo (para reler o JPEG depois)
    deteccoes: list[Deteccao]
    poses: list[Pose]  # a principal primeiro
    zonas: dict[str, list[Deteccao]] = field(default_factory=dict)


class Detector(Protocol):
    def __call__(self, frame: np.ndarray) -> list[Deteccao]: ...


class Yolo:
    def __init__(self, conf: float = 0.25) -> None:
        from ultralytics import YOLO

        self.conf = conf
        self.modelo = YOLO(str(_caminho_yolo(get_settings().yolo_model)))
        self.nomes = self.modelo.names
        threads_opencv()

    def __call__(self, frame: np.ndarray) -> list[Deteccao]:
        r = self.modelo.predict(frame, verbose=False, conf=self.conf)[0]
        b = r.boxes
        if b is None or len(b) == 0:
            return []
        return [
            Deteccao(self.nomes[int(c)], float(p), tuple(float(v) for v in xy))
            for c, p, xy in zip(b.cls.cpu().numpy(), b.conf.cpu().numpy(), b.xyxy.cpu().numpy(),
                                strict=False)
        ]  # fmt: skip


_detector: Detector | None = None


def carregar_detector() -> Detector:
    global _detector
    if _detector is None:
        _detector = Yolo()
    return _detector


# --- áreas críticas -------------------------------------------------------------------------
Poligono = list[tuple[float, float]]  # vértices normalizados (0..1) em relação ao quadro


def ponto_em_poligono(x: float, y: float, poligono: Poligono) -> bool:
    """Teste par-ímpar (ray casting); ``poligono`` e o ponto na mesma escala."""
    dentro = False
    n = len(poligono)
    for i in range(n):
        (x1, y1), (x2, y2) = poligono[i], poligono[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            dentro = not dentro
    return dentro


def ponto_de_apoio(d: Deteccao) -> tuple[float, float]:
    """Pessoa: pés (centro da base da caixa); objeto: centro da caixa."""
    x1, y1, x2, y2 = d.caixa
    return ((x1 + x2) / 2, y2 if d.rotulo == "person" else (y1 + y2) / 2)


def zonas_do_quadro(deteccoes: list[Deteccao], zonas: dict[str, Poligono], w: int, h: int):
    """Detecções dentro de cada zona: ``{zona: [Deteccao, ...]}``."""
    saida: dict[str, list[Deteccao]] = {}
    for nome, poly in zonas.items():
        saida[nome] = [
            d for d in deteccoes if ponto_em_poligono(*_norm(ponto_de_apoio(d), w, h), poly)
        ]
    return saida


def _norm(p: tuple[float, float], w: int, h: int) -> tuple[float, float]:
    return p[0] / w, p[1] / h
