"""Comandos `python -m asclepio_multimodal video ...` (imports pesados ficam dentro dos comandos)."""

from __future__ import annotations

from pathlib import Path

import typer

app = typer.Typer(help="video", no_args_is_help=True, add_completion=False)


@app.command()
def analyze(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False, help="Vídeo a analisar"),
    profile: str = typer.Option(
        "fisioterapia", "--profile", help="fisioterapia | quarto | cirurgia"
    ),
    exercise: str = typer.Option(
        "agachamento", "--exercise", help="Exercício (perfil fisioterapia)"
    ),
    out: Path | None = typer.Option(
        None, "--out", help="Pasta de saída (padrão: data/analyses/video/<nome>)"
    ),
    sample_fps: float | None = typer.Option(
        None, "--sample-fps", help="Quadros analisados por segundo"
    ),
    regiao: str | None = typer.Option(None, "--regiao", help="Recorte 'x0,y0,x1,y1' normalizado"),
) -> None:
    """Analisa um vídeo, grava o relatório e imprime o resumo e os achados."""
    from rich.console import Console
    from rich.table import Table

    from ..config import get_settings
    from ..media import MediaError
    from . import analyze_video

    console = Console()
    destino = out or get_settings().analyses_dir / "video" / arquivo.stem
    rec = tuple(float(v) for v in regiao.split(",")) if regiao else None
    try:
        r = analyze_video(
            arquivo, destino, profile, exercise=exercise if profile == "fisioterapia" else None,
            sample_fps=sample_fps, regiao=rec,  # type: ignore[arg-type]
            progress=lambda f, e: console.print(f"[dim]{f:4.0%} {e}[/]"),
        )  # fmt: skip
    except (MediaError, ValueError) as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1) from e
    console.print(
        f"\n[bold]{r.summary}[/]  risco={r.risk_level} ({r.risk_score:.2f})  {r.processing_ms} ms"
    )
    for w in r.warnings:
        console.print(f"[yellow]! {w}[/]")
    if r.findings:
        tab = Table("severidade", "achado", "trecho (s)", "recomendação")
        for f in r.findings:
            tab.add_row(f.severity, f.title, f"{f.t_start}–{f.t_end}", f.recommendation or "")
        console.print(tab)
    console.print(f"Relatório e artefatos em [cyan]{destino}[/]")


@app.command()
def evaluate(
    quedas: int = typer.Option(30, "--quedas", help="Quantas sequências fall-XX (máx. 30)"),
    adl: int = typer.Option(40, "--adl", help="Quantas sequências adl-XX (máx. 40)"),
    sample_fps: float | None = typer.Option(None, "--sample-fps"),
) -> None:
    """Avalia no UR Fall Detection (quarto) e nos vídeos de agachamento; grava video_eval.json."""
    from rich.console import Console

    from .evaluate import executar

    console = Console()
    rel = executar(quedas, adl, sample_fps, log=console.print)
    u = rel["urfd"]
    console.print(
        f"\nURFD n={u['n_videos']}  sens={u['sensibilidade']}  espec={u['especificidade']}  "
        f"acc={u['acuracia']}  F1={u['f1']}  {u['matriz_confusao']}"
    )
    console.print("Relatório: multimodal/reports/video_eval.json")
