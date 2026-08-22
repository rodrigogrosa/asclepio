from __future__ import annotations

from pathlib import Path

from asclepio_ml.cli import app
from typer.testing import CliRunner

runner = CliRunner()


def test_help_lists_commands():
    res = runner.invoke(app, ["--help"])
    assert res.exit_code == 0
    for cmd in ("prepare", "train", "export", "evaluate", "all", "synthetic-patients"):
        assert cmd in res.stdout


def test_prepare_command(tmp_config: Path, tmp_path: Path):
    out = tmp_path / "out"
    res = runner.invoke(app, ["prepare", "-c", str(tmp_config), "-o", str(out), "--seed", "3"])
    assert res.exit_code == 0, res.stdout
    assert (out / "train.jsonl").exists() and (out / "DATASET_CARD.md").exists()


def test_synthetic_patients(tmp_path: Path):
    res = runner.invoke(app, ["synthetic-patients", "-o", str(tmp_path / "patients.json")])
    assert res.exit_code == 0, res.stdout
    assert (tmp_path / "patients.json").stat().st_size > 1000
