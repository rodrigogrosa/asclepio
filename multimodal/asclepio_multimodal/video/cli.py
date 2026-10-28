"""Comandos `python -m asclepio_multimodal video ...` (imports pesados ficam dentro dos comandos)."""

from __future__ import annotations

import typer

app = typer.Typer(help="video", no_args_is_help=True, add_completion=False)
