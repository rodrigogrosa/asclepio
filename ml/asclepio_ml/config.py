"""Carregamento da configuração (``ml/configs/finetune.yaml``) e resolução de caminhos.

Decisão: um único YAML com *perfis* de treino (``quick`` para smoke test, ``full`` para a
execução real). A CLI permite sobrescrever ``base_model`` e diretório de saída.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# Raiz do monorepo: .../asclepio (este arquivo está em ml/asclepio_ml/config.py)
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = REPO_ROOT / "ml" / "configs" / "finetune.yaml"


@dataclass
class Paths:
    knowledge_base: Path
    seed_instructions: Path
    processed: Path
    runs: Path
    models: Path
    reports: Path
    assets: Path
    registry: Path
    cache: Path

    @classmethod
    def from_dict(cls, d: dict[str, str], root: Path) -> Paths:
        def r(key: str, default: str) -> Path:
            p = Path(d.get(key, default))
            return p if p.is_absolute() else root / p

        return cls(
            knowledge_base=r("knowledge_base", "data/knowledge_base"),
            seed_instructions=r("seed_instructions", "data/synthetic/instructions_seed.jsonl"),
            processed=r("processed", "data/processed"),
            runs=r("runs", "ml/runs"),
            models=r("models", "ml/models"),
            reports=r("reports", "ml/reports"),
            assets=r("assets", "docs/assets/eval"),
            registry=r("registry", "ml/registry.json"),
            cache=r("cache", "ml/.cache"),
        )


@dataclass
class TrainProfile:
    name: str
    max_seq_len: int = 1024
    epochs: float = 2
    max_steps: int = -1
    batch_size: int = 4
    grad_accum: int = 4
    learning_rate: float = 2e-4
    lr_scheduler: str = "cosine"
    warmup_ratio: float = 0.05
    weight_decay: float = 0.0
    logging_steps: int = 10
    eval_steps: int = 50
    eval_subset: int = 64  # nº de exemplos do val usados na curva de eval durante o treino
    save_steps: int = 0
    gradient_checkpointing: bool = False
    dtype: str = "auto"

    @classmethod
    def from_dict(cls, name: str, d: dict[str, Any]) -> TrainProfile:
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(name=name, **known)


@dataclass
class Config:
    base_model: str
    seed: int
    paths: Paths
    prepare: dict[str, Any]
    lora: dict[str, Any]
    profiles: dict[str, TrainProfile]
    export: dict[str, Any]
    evaluate: dict[str, Any]
    raw: dict[str, Any] = field(default_factory=dict)
    root: Path = REPO_ROOT

    def profile(self, name: str) -> TrainProfile:
        if name not in self.profiles:
            raise KeyError(f"Perfil '{name}' não existe. Disponíveis: {', '.join(self.profiles)}")
        return self.profiles[name]


def load_config(path: str | Path | None = None, root: Path | None = None) -> Config:
    """Lê o YAML e devolve um ``Config``. ``root`` permite testes com diretórios temporários."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG_PATH
    root = Path(root) if root else REPO_ROOT
    with cfg_path.open(encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    profiles = {
        n: TrainProfile.from_dict(n, d or {}) for n, d in (raw.get("profiles") or {}).items()
    }
    return Config(
        base_model=os.environ.get("ASCLEPIO_BASE_MODEL")
        or raw.get("base_model", "Qwen/Qwen2.5-0.5B-Instruct"),
        seed=int(raw.get("seed", 42)),
        paths=Paths.from_dict(raw.get("paths") or {}, root),
        prepare=raw.get("prepare") or {},
        lora=raw.get("lora") or {},
        profiles=profiles,
        export=raw.get("export") or {},
        evaluate=raw.get("evaluate") or {},
        raw=raw,
        root=root,
    )
