"""Estimativa de pose COCO de 18 pontos (ordem do OpenPose).

Backend ``openpose``: abordagem top-down — o YOLOv8 acha as pessoas, cada recorte (com margem) vai
à rede OpenPose (Caffe, via OpenCV DNN) e o ponto de cada articulação é o máximo do seu mapa de
calor. Backend ``yolov8-pose``: COCO 17 convertido para 18 (pescoço = meio dos ombros).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np

from ..assets import ASSETS, ensure
from ..config import get_settings

NARIZ, PESCOCO = 0, 1
OMBRO_D, COTOVELO_D, PUNHO_D = 2, 3, 4
OMBRO_E, COTOVELO_E, PUNHO_E = 5, 6, 7
QUADRIL_D, JOELHO_D, TORNOZELO_D = 8, 9, 10
QUADRIL_E, JOELHO_E, TORNOZELO_E = 11, 12, 13

# Arestas do esqueleto para o desenho (pares de índices COCO-18)
ESQUELETO = [
    (1, 2), (2, 3), (3, 4), (1, 5), (5, 6), (6, 7), (1, 8), (8, 9), (9, 10), (1, 11),
    (11, 12), (12, 13), (1, 0), (0, 14), (14, 16), (0, 15), (15, 17),
]  # fmt: skip

# COCO-17 (Ultralytics) → COCO-18 (OpenPose); o pescoço é calculado
_YOLO_PARA_OP = [0, -1, 6, 8, 10, 5, 7, 9, 12, 14, 16, 11, 13, 15, 2, 1, 4, 3]

Caixa = tuple[float, float, float, float]  # x1, y1, x2, y2 em pixels


def threads_opencv() -> None:
    """O Ultralytics zera os threads do OpenCV ao ser importado, o que deixa o OpenPose (OpenCV
    DNN) ~6x mais lento; religa depois de qualquer import dele."""
    import os

    import cv2

    cv2.setNumThreads(min(8, os.cpu_count() or 1))


@dataclass
class Pose:
    kpts: np.ndarray  # (18, 3): x, y, confiança
    box: Caixa
    score: float


class Estimador(Protocol):
    nome: str
    conf_min: float

    def __call__(self, frame: np.ndarray, caixas: list[Caixa]) -> list[Pose]: ...


def _pose_de(kpts: np.ndarray, box: Caixa, conf_min: float) -> Pose:
    ok = kpts[:, 2] >= conf_min
    return Pose(kpts, box, float(kpts[ok, 2].mean()) if ok.any() else 0.0)


class OpenPose:
    """OpenPose COCO (CMU) carregado uma vez; um recorte por pessoa."""

    nome = "openpose"

    def __init__(self, conf_min: float = 0.1, lado: int = 368, margem: float = 0.15) -> None:
        import cv2

        self.conf_min, self.lado, self.margem = conf_min, lado, margem
        proto, pesos = ensure("openpose_prototxt"), ensure("openpose_caffemodel")
        self.rede = cv2.dnn.readNetFromCaffe(str(proto), str(pesos))
        threads_opencv()

    def __call__(self, frame: np.ndarray, caixas: list[Caixa]) -> list[Pose]:
        import cv2

        h, w = frame.shape[:2]
        saida = []
        for x1, y1, x2, y2 in caixas:
            mx, my = (x2 - x1) * self.margem, (y2 - y1) * self.margem
            cx1, cy1 = max(0, int(x1 - mx)), max(0, int(y1 - my))
            cx2, cy2 = min(w, int(x2 + mx)), min(h, int(y2 + my))
            ch, cw = cy2 - cy1, cx2 - cx1
            if ch < 16 or cw < 16:
                continue
            # lado maior = 368 px; a rede é totalmente convolucional (passo 8), então cabe qualquer razão
            esc = self.lado / max(ch, cw)
            iw, ih = (max(64, round(d * esc / 8) * 8) for d in (cw, ch))
            blob = cv2.dnn.blobFromImage(frame[cy1:cy2, cx1:cx2], 1 / 255, (iw, ih), (0, 0, 0))
            self.rede.setInput(blob)
            mapas = self.rede.forward()[0, :18]  # (18, h', w'): o 19º canal é o fundo
            mh, mw = mapas.shape[1:]
            plano = mapas.reshape(18, -1)
            idx, conf = plano.argmax(1), plano.max(1)
            ys, xs = np.divmod(idx, mw)
            k = np.stack([cx1 + (xs + 0.5) * cw / mw, cy1 + (ys + 0.5) * ch / mh, conf], axis=1)
            saida.append(_pose_de(k, (x1, y1, x2, y2), self.conf_min))
        return saida


class YoloPose:
    """YOLOv8-pose no quadro inteiro (ignora as caixas recebidas)."""

    nome = "yolov8-pose"

    def __init__(self, conf_min: float = 0.3) -> None:
        from ultralytics import YOLO

        s = get_settings()
        self.conf_min = conf_min
        self.modelo = YOLO(str(_caminho_yolo(s.yolo_pose_model)))
        threads_opencv()

    def __call__(self, frame: np.ndarray, caixas: list[Caixa]) -> list[Pose]:
        r = self.modelo.predict(frame, verbose=False, conf=0.25)[0]
        if r.keypoints is None or r.boxes is None:
            return []
        saida = []
        for kp, bx in zip(r.keypoints.data.cpu().numpy(), r.boxes.xyxy.cpu().numpy(), strict=False):
            k = np.zeros((18, 3))
            for op, co in enumerate(_YOLO_PARA_OP):
                if co >= 0:
                    k[op] = kp[co]
            ombros = kp[[5, 6]]
            k[PESCOCO] = [*ombros[:, :2].mean(0), ombros[:, 2].min()]
            saida.append(_pose_de(k, tuple(float(v) for v in bx), self.conf_min))
        return saida


def _caminho_yolo(nome: str) -> Path:
    """Pesos do YOLO em ``models_dir/yolo``; baixa (com checksum) se for um ativo conhecido."""
    p = get_settings().models_dir / "yolo" / nome
    if p.exists():
        return p
    for a in ASSETS:
        if a.relpath == f"yolo/{nome}":
            return ensure(a.key)
    raise FileNotFoundError(f"Pesos '{nome}' não encontrados em {p.parent}")


_cache: dict[str, Estimador] = {}


def carregar_estimador() -> Estimador:
    """Carrega a rede uma única vez por processo, conforme ``settings.pose_backend``."""
    backend = get_settings().pose_backend
    if backend not in _cache:
        _cache[backend] = YoloPose() if backend == "yolov8-pose" else OpenPose()
    return _cache[backend]
