"""Utilitários: dispositivo/dtype, I/O de JSONL, normalização de texto, logging com rich."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any

from rich.console import Console

console = Console()


def log(msg: str, style: str = "") -> None:
    console.print(f"[bold magenta]asclepio-ml[/] {msg}", style=style, highlight=False)


# ---------------------------------------------------------------------------
# Dispositivo e dtype
# ---------------------------------------------------------------------------
def get_device(prefer: str | None = None) -> str:
    """cuda → mps → cpu (ou o que for pedido explicitamente, se disponível)."""
    import torch

    if prefer and prefer != "auto":
        return prefer
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def resolve_dtype(device: str, dtype: str = "auto"):
    """Por que fp32 em MPS? bf16/fp16 em MPS ainda tem operações sem suporte ou instáveis
    (NaN em atenção/LayerNorm em algumas versões); para um modelo de 0,5 B parâmetros o
    fp32 cabe folgado em 48 GB e evita surpresas. Em CUDA usamos bf16 (padrão da indústria)."""
    import torch

    table = {
        "float32": torch.float32,
        "fp32": torch.float32,
        "bfloat16": torch.bfloat16,
        "bf16": torch.bfloat16,
        "float16": torch.float16,
        "fp16": torch.float16,
    }
    if dtype != "auto":
        return table[dtype]
    if device == "cuda":
        return torch.bfloat16
    return torch.float32


# ---------------------------------------------------------------------------
# JSONL
# ---------------------------------------------------------------------------
def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return []
    out: list[dict[str, Any]] = []
    with p.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> int:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with p.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def write_json(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: str | Path) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Texto
# ---------------------------------------------------------------------------
def strip_accents(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in s if not unicodedata.combining(c))


def normalize(s: str) -> str:
    """Normalização para dedupe: minúsculas, sem acentos, sem pontuação, espaços únicos."""
    s = strip_accents(s).lower()
    s = re.sub(r"[^a-z0-9%/,.\- ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def short_hash(s: str, n: int = 10) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:n]  # noqa: S324 — não é criptografia


def truncate_at_boundary(text: str, max_chars: int) -> str:
    """Corta em limite de parágrafo/linha/frase para não deixar resposta 'picada'."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    for sep in ("\n\n", "\n", ". "):
        i = cut.rfind(sep)
        if i > max_chars * 0.5:
            return cut[: i + (1 if sep == ". " else 0)].rstrip()
    return cut.rstrip()


def batched(items: list[Any], size: int) -> Iterator[list[Any]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]
