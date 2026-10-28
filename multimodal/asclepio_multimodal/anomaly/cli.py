"""Comandos `python -m asclepio_multimodal anomaly ...` (imports pesados ficam dentro dos comandos)."""

from __future__ import annotations

import typer

app = typer.Typer(help="anomaly", no_args_is_help=True, add_completion=False)
