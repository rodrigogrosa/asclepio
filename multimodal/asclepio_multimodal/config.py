"""Configuração da Fase 4 (12-factor): variáveis de ambiente / .env com defaults seguros.

As chaves do Azure ficam só no ``.env`` (nunca no código). Sem chave, cada serviço cai para o
equivalente local e o resultado declara isso em ``warnings`` — a análise não para.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# Raiz do monorepo: .../asclepio (este arquivo está em multimodal/asclepio_multimodal/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]


class MultimodalSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- diretórios (data/ é volume no Docker) ---
    models_dir: Path = REPO_ROOT / "data" / "models"
    samples_dir: Path = REPO_ROOT / "data" / "samples"
    datasets_dir: Path = REPO_ROOT / "data" / "datasets"
    analyses_dir: Path = REPO_ROOT / "data" / "analyses"

    # --- vídeo ---
    video_sample_fps: float = 5.0
    video_max_seconds: float = 300.0
    pose_backend: Literal["openpose", "yolov8-pose"] = "openpose"
    yolo_model: str = "yolov8n.pt"
    yolo_pose_model: str = "yolov8n-pose.pt"

    # --- áudio / texto ---
    stt_provider: Literal["auto", "azure", "local"] = "auto"
    text_provider: Literal["auto", "azure", "local"] = "auto"
    speech_language: str = "pt-BR"
    azure_speech_key: SecretStr | None = None
    azure_speech_region: str = "brazilsouth"
    azure_language_key: SecretStr | None = None
    azure_language_endpoint: str | None = None
    whisper_model: str = "openai/whisper-small"
    audio_events_enabled: bool = True
    audio_events_model: str = "MIT/ast-finetuned-audioset-10-10-0.4593"

    @property
    def azure_speech_ready(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_key.get_secret_value())

    @property
    def azure_language_ready(self) -> bool:
        return bool(
            self.azure_language_key
            and self.azure_language_key.get_secret_value()
            and self.azure_language_endpoint
        )

    def use_azure_speech(self) -> bool:
        return self.stt_provider == "azure" or (
            self.stt_provider == "auto" and self.azure_speech_ready
        )

    def use_azure_language(self) -> bool:
        return self.text_provider == "azure" or (
            self.text_provider == "auto" and self.azure_language_ready
        )


@lru_cache
def get_settings() -> MultimodalSettings:
    s = MultimodalSettings()
    # Modelos do Hugging Face (AST/AudioSet, Whisper) ficam junto dos demais, no volume de dados
    os.environ.setdefault("HF_HOME", str(s.models_dir / "hf"))
    # Ultralytics não deve escrever configuração fora do volume (container com usuário não-root)
    os.environ.setdefault("YOLO_CONFIG_DIR", str(s.models_dir / "yolo"))
    return s
