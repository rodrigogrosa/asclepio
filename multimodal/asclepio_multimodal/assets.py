"""Ativos externos da Fase 4 (pesos de modelos e mídias de demonstração) com origem, licença e
checksum. Nada disso vai para o Git: é baixado sob demanda para ``data/`` e conferido por SHA-256.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx

from .config import get_settings


@dataclass(frozen=True)
class Asset:
    key: str
    group: str  # "models" | "samples"
    relpath: str  # relativo a models_dir ou samples_dir
    url: str
    sha256: str
    license: str
    source: str  # citação curta para o relatório

    @property
    def path(self) -> Path:
        s = get_settings()
        base = s.models_dir if self.group == "models" else s.samples_dir
        return base / self.relpath


ASSETS: list[Asset] = [
    # --- modelos de vídeo ---
    Asset(
        "openpose_prototxt",
        "models",
        "openpose/pose_deploy_linevec.prototxt",
        "https://raw.githubusercontent.com/CMU-Perceptual-Computing-Lab/openpose/master/models/pose/coco/pose_deploy_linevec.prototxt",
        "17051b87f709aa094e09c5da7b78e9016a1f37b2b452ed1f190fe74cce70b1ad",
        "OpenPose — licença acadêmica não comercial (CMU)",
        "Cao et al., OpenPose (CVPR 2017 / TPAMI 2019) — modelo COCO 18 pontos",
    ),
    Asset(
        "openpose_caffemodel",
        "models",
        "openpose/pose_iter_440000.caffemodel",
        # espelho do arquivo oficial da CMU (MD5 5156d31f670511fce9b4e28b403f2939, igual ao getModels.sh)
        "https://huggingface.co/Tlaloc-Es/openpose/resolve/main/pose_iter_440000.caffemodel",
        "b4cf475576abd7b15d5316f1ee65eb492b5c9f5865e70a2e7882ed31fb682549",
        "OpenPose — licença acadêmica não comercial (CMU)",
        "Cao et al., OpenPose — pesos COCO pose_iter_440000",
    ),
    Asset(
        "yolov8n",
        "models",
        "yolo/yolov8n.pt",
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n.pt",
        "f59b3d833e2ff32e194b5bb8e08d211dc7c5bdf144b90d2c8412c47ccfc83b36",
        "AGPL-3.0 (Ultralytics)",
        "Jocher et al., Ultralytics YOLOv8 (2023) — COCO 80 classes",
    ),
    Asset(
        "yolov8n_pose",
        "models",
        "yolo/yolov8n-pose.pt",
        "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8n-pose.pt",
        "c6fa93dd1ee4a2c18c900a45c1d864a1c6f7aba75d84f91648a30b7fb641d212",
        "AGPL-3.0 (Ultralytics)",
        "Ultralytics YOLOv8-pose (COCO keypoints) — alternativa rápida ao OpenPose",
    ),
    # --- vídeos de demonstração (licenças abertas; créditos no relatório) ---
    Asset(
        "video_squat",
        "samples",
        "video/squat_demo.webm",
        "https://upload.wikimedia.org/wikipedia/commons/5/5c/Squat_-_exercise_demonstration_video.webm",
        "2440985661c3533a4ce78472b0f4577dbdf023aff3f8f9a225bbb5ff8071b1e9",
        "CC BY 3.0",
        "Wikimedia Commons — 'Squat - exercise demonstration video' (FitnessScience)",
    ),
    Asset(
        "video_single_leg_squat",
        "samples",
        "video/single_leg_squat.webm",
        "https://upload.wikimedia.org/wikipedia/commons/1/16/Basic_single_leg_squat.webm",
        "ab4602823ad00de3409eb50d2c65c6b1ce5566c5dca6753555ff2b19107db88e",
        "CC BY-SA 4.0",
        "Wikimedia Commons — 'Basic single leg squat' (RickyBennison)",
    ),
    Asset(
        "video_squat_side",
        "samples",
        "video/kettlebell_squat_side.webm",
        "https://upload.wikimedia.org/wikipedia/commons/9/93/Kettlebell_Racked_Squats_%28side_view%29.webm",
        "5e0ded0810d73db0acfb3bbdf71a181e512607db16c1fde8d2ed30bb18ca840d",
        "CC BY-SA 4.0",
        "Wikimedia Commons — 'Kettlebell Racked Squats (side view)' (Taco fleur)",
    ),
    Asset(
        "video_fall",
        "samples",
        "video/urfd_fall-01-cam0.mp4",
        "http://fenix.ur.edu.pl/~mkepski/ds/data/fall-01-cam0.mp4",
        "5fcb77e5b5a35d73ab8cda856ea58bd9e6acd7552e16fc6d22a623556bee76bc",
        "Uso em pesquisa (URFD)",
        "Kwolek & Kepski, UR Fall Detection Dataset (2014) — sequência fall-01, câmera 0",
    ),
    Asset(
        "video_adl",
        "samples",
        "video/urfd_adl-01-cam0.mp4",
        "http://fenix.ur.edu.pl/~mkepski/ds/data/adl-01-cam0.mp4",
        "b7b0220c8081a9a8b284174f55b7ca56e5bf9a525af1bfda0ae29c73d06016f8",
        "Uso em pesquisa (URFD)",
        "Kwolek & Kepski, UR Fall Detection Dataset (2014) — sequência adl-01 (atividade normal)",
    ),
]

BY_KEY: dict[str, Asset] = {a.key: a for a in ASSETS}


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure(key: str) -> Path:
    """Devolve o caminho do ativo, baixando e conferindo o SHA-256 se ainda não existir."""
    a = BY_KEY[key]
    dst = a.path
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_suffix(dst.suffix + ".part")
    with httpx.stream("GET", a.url, follow_redirects=True, timeout=120) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_bytes(1 << 20):
                f.write(chunk)
    got = sha256_of(tmp)
    if got != a.sha256:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum inválido para {key}: esperado {a.sha256}, obtido {got}")
    tmp.rename(dst)
    return dst


def ensure_group(group: str) -> list[Path]:
    return [ensure(a.key) for a in ASSETS if group in ("all", a.group)]
