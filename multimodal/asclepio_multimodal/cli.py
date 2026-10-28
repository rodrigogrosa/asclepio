"""CLI da Fase 4: ``uv run python -m asclepio_multimodal <grupo> <comando>``.

Grupos: ``assets`` (baixa pesos e mídias de demonstração) · ``video`` · ``audio`` · ``anomaly``.
"""

from __future__ import annotations

import typer
from rich.console import Console

from .anomaly.cli import app as anomaly_app
from .audio.cli import app as audio_app
from .video.cli import app as video_app

console = Console()
app = typer.Typer(
    help="Asclépio · Fase 4 — monitoramento multimodal (vídeo, áudio, anomalias, fusão).",
    no_args_is_help=True,
    add_completion=False,
)
app.add_typer(video_app, name="video", help="Análise de vídeo (OpenPose + YOLOv8).")
app.add_typer(audio_app, name="audio", help="Análise de áudio (Azure Speech/Text Analytics + voz).")
app.add_typer(
    anomaly_app, name="anomaly", help="Anomalias em sinais vitais, prescrições e mobilidade."
)


@app.command()
def assets(group: str = typer.Argument("all", help="models | samples | all")) -> None:
    """Baixa (se faltar) e confere por SHA-256 os pesos dos modelos e as mídias de demonstração."""
    from .assets import ASSETS, ensure

    for a in ASSETS:
        if group in ("all", a.group):
            p = ensure(a.key)
            console.print(f"[green]ok[/] {a.key:24} {p.stat().st_size / 1e6:8.1f} MB  {a.license}")
