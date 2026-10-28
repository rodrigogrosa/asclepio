"""Comandos `python -m asclepio_multimodal anomaly ...` (imports pesados ficam dentro dos comandos)."""

from __future__ import annotations

import typer

app = typer.Typer(help="anomaly", no_args_is_help=True, add_completion=False)


@app.command()
def fontes() -> None:
    """Lista as fontes de sinais vitais ao vivo (LIVE_SOURCES)."""
    from . import LIVE_SOURCES

    for k, v in LIVE_SOURCES.items():
        typer.echo(f"{k:26} {v}")


@app.command()
def vitals(
    fonte: str = typer.Argument(
        ..., help="sintetico:sepse | sintetico:dessaturacao | physionet:<registro>"
    ),
    sem_antiflood: bool = typer.Option(
        False, "--sem-antiflood", help="Mostra todos os alertas brutos"
    ),
) -> None:
    """Reproduz a série pelo detector em fluxo e imprime cada achado quando ele ocorre."""
    from datetime import datetime

    from rich.console import Console
    from rich.table import Table

    from . import load_live_source
    from .vitals import OnlineVitalsDetector

    start = datetime(2026, 8, 21, 8, 0)
    samples = load_live_source(fonte, start=start)
    det = OnlineVitalsDetector(antiflood=not sem_antiflood)
    tab = Table(title=f"{fonte} — {len(samples)} amostras")
    for c in ("min", "severidade", "código", "achado", "escore"):
        tab.add_column(c)
    n = 0
    for s in samples:
        for f in det.update(s):
            n += 1
            cor = "red" if f.severity == "critico" else "yellow"
            tab.add_row(
                f"{(s.at - start).total_seconds() / 60:.0f}",
                f"[{cor}]{f.severity}[/]",
                f.code,
                f.title,
                f"{det.score:.2f}",
            )
    Console().print(tab)
    typer.echo(
        f"{n} alerta{'' if n == 1 else 's'} · escore final {det.score:.2f} · NEWS2 final {det.news2_score}"
    )
    if fonte.startswith("sintetico:"):
        from .synthetic import synthetic_onset_index

        i = synthetic_onset_index(fonte.split(":", 1)[1], len(samples))
        typer.echo(
            "gabarito: " + ("sem anomalia" if i is None else f"anomalia começa no minuto {i}")
        )


@app.command()
def fetch(
    registros: list[str] = typer.Argument(
        None, help="ex.: 201 202 (padrão: as fontes ao vivo do PhysioNet)"
    ),
) -> None:
    """Baixa para o cache (data/datasets/physionet) os registros do PhysioNet."""
    from . import LIVE_SOURCES
    from .physionet import fetch_record

    for r in registros or [k.split(":", 1)[1] for k in LIVE_SOURCES if k.startswith("physionet:")]:
        typer.echo(f"{r}: {fetch_record(r)}")


@app.command()
def evaluate(
    figuras: bool = typer.Option(
        True, "--figuras/--sem-figuras", help="Gera as figuras em docs/assets/fase4/anomaly"
    ),
) -> None:
    """Avalia nos registros reais do PhysioNet, na injeção controlada e nos pacientes sintéticos."""
    from .evaluate import run_all

    run_all(make_figures=figuras, log=typer.echo)
