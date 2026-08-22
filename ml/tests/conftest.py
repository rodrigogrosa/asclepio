"""Fixtures compartilhadas: configuração apontando para a mini base de conhecimento de teste."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

FIXTURES = Path(__file__).parent / "fixtures"
CONFIG_PATH = Path(__file__).resolve().parents[1] / "configs" / "finetune.yaml"


@pytest.fixture
def fixture_kb() -> Path:
    return FIXTURES / "knowledge_base"


@pytest.fixture
def fixture_seed() -> Path:
    return FIXTURES / "synthetic" / "instructions_seed.jsonl"


@pytest.fixture
def tmp_config(tmp_path: Path) -> Path:
    """YAML igual ao oficial, mas com caminhos em tmp_path (e KB/seed das fixtures)."""
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    raw["paths"] = {
        "knowledge_base": str(FIXTURES / "knowledge_base"),
        "seed_instructions": str(FIXTURES / "synthetic" / "instructions_seed.jsonl"),
        "processed": str(tmp_path / "processed"),
        "runs": str(tmp_path / "runs"),
        "models": str(tmp_path / "models"),
        "reports": str(tmp_path / "reports"),
        "assets": str(tmp_path / "assets"),
        "registry": str(tmp_path / "registry.json"),
        "cache": str(tmp_path / "cache"),
    }
    raw["prepare"]["cap_per_category"] = 60
    p = tmp_path / "finetune.yaml"
    p.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return p
