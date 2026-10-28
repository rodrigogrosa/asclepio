"""Comandos `python -m asclepio_multimodal audio ...` (imports pesados ficam dentro dos comandos)."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

app = typer.Typer(help="audio", no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def analyze(
    arquivo: Path = typer.Argument(..., exists=True, dir_okay=False, help="WAV, MP3, M4A, OGG…"),
    out: Path = typer.Option(Path("data/analyses/audio"), "--out", help="Pasta dos artefatos."),
    language: str = typer.Option(None, "--language", help="Padrão: SPEECH_LANGUAGE (pt-BR)."),
) -> None:
    """Analisa um áudio de consulta: transcrição, termos críticos, voz, eventos e relatório."""
    from . import analyze_audio

    with console.status("Analisando…"):
        res = analyze_audio(arquivo, out, language=language)
    console.print(f"[bold]{res.summary}[/]")
    console.print(f"Risco: {res.risk_level} ({res.risk_score:.2f}) · severidade: {res.severity}")
    for f in res.findings:
        console.print(f"  \\[{f.severity}] {f.title}")
    for w in res.warnings:
        console.print(f"[yellow]aviso:[/] {w}")
    console.print(f"Relatório: {out / res.artifacts['report']}")


@app.command()
def samples(
    out: Path = typer.Option(
        Path("data/samples/audio"), "--out", help="Pasta dos WAV de demonstração."
    ),
) -> None:
    """Gera as 3 consultas sintéticas (normal, fadiga, dispneia) com o `say` do macOS."""
    from .samples import generate_samples

    try:
        paths = generate_samples(out)
    except RuntimeError as exc:
        console.print(f"[red]{exc}[/]")
        raise typer.Exit(1) from exc
    for p in paths:
        console.print(f"[green]ok[/] {p} ({p.stat().st_size / 1e3:.0f} kB)")


@app.command()
def evaluate(
    out: Path = typer.Option(
        None, "--out", help="JSON (padrão: multimodal/reports/audio_eval.json)."
    ),
    figs: Path = typer.Option(None, "--figs", help="Figuras (padrão: docs/assets/fase4/audio)."),
    download: bool = typer.Option(True, help="Baixar VOICED e FLEURS se faltarem."),
    esc50: bool = typer.Option(True, help="Validar o detector de eventos no ESC-50."),
    demos: bool = typer.Option(True, help="Rodar as 3 consultas de demonstração."),
    fleurs: bool = typer.Option(True, help="Medir a referência de fala no FLEURS pt-BR."),
) -> None:
    """Avalia com dados públicos: VOICED (PhysioNet), FLEURS, ESC-50 e as consultas sintéticas."""
    from .evaluation import DEFAULT_FIGS, DEFAULT_OUT, run_evaluation

    rep = run_evaluation(
        out or DEFAULT_OUT,
        figs or DEFAULT_FIGS,
        download=download,
        esc50=esc50,
        demos=demos,
        fleurs=fleurs,
    )
    c = rep["voiced"]["classificador"]
    console.print(
        f"VOICED: AUC {c['auc']:.3f} · acurácia {c['acuracia']:.3f} · sensibilidade "
        f"{c['sensibilidade']:.3f} · especificidade {c['especificidade']:.3f}"
    )
    console.print(f"Relatório salvo em {out or DEFAULT_OUT}")
