"""Gera docs/RELATORIO_TECNICO.pdf a partir dos Markdown (relatório + anexos) com diagramas Mermaid
renderizados e gráficos embutidos. Requer Google Chrome (headless) instalado.

Uso: uv run --with markdown python scripts/build_report_pdf.py  (ou `make docs-pdf`)
"""

from __future__ import annotations

import base64
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

import markdown

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

# Documentos disponíveis: `python scripts/build_report_pdf.py [relatorio|guia] [out_dir]`
DOC_KIND = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("/") else "relatorio"
OUT_DIR = Path(sys.argv[2]) if len(sys.argv) > 2 else (Path(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].startswith("/") else DOCS)

DOCUMENTS = {
    "relatorio": {
        "out": "RELATORIO_TECNICO.pdf",
        "title": "Relatório Técnico",
        "subtitle": "LLM fine-tunada · LangChain/LangGraph · Guardrails · RAG com fontes · Auditoria",
        "sections": [
            ("", DOCS / "RELATORIO_TECNICO.md"),
            ("Anexo A — Fine-tuning em detalhe", DOCS / "FINE_TUNING.md"),
            ("Anexo B — Arquitetura", DOCS / "ARQUITETURA.md"),
            ("Anexo C — Políticas de segurança e acesso", DOCS / "POLITICAS.md"),
            ("Anexo D — Evidências: onde cada exigência aparece", DOCS / "EVIDENCIAS.md"),
        ],
    },
    "guia": {
        "out": "GUIA_INSTALACAO.pdf",
        "title": "Guia de Instalação",
        "subtitle": "Passo a passo para instalar e avaliar o Asclépio em qualquer máquina (macOS · Linux · Windows/WSL2)",
        "sections": [("", DOCS / "GUIA_INSTALACAO.md"), ("Anexo — Evidências: onde cada exigência aparece", DOCS / "EVIDENCIAS.md")],
    },
}
DOC = DOCUMENTS[DOC_KIND]
OUT_PDF = OUT_DIR / DOC["out"]
SECTIONS = DOC["sections"]

CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
html { -webkit-print-color-adjust: exact; }
body { font-family: -apple-system, "Inter", "Helvetica Neue", Arial, sans-serif; font-size: 10.5pt; line-height: 1.45; color: #1a1a1a; }
h1, h2, h3, h4 { font-family: "Montserrat", -apple-system, Arial, sans-serif; color: #0B0B10; page-break-after: avoid; }
h1 { font-size: 22pt; border-bottom: 3px solid #ED145B; padding-bottom: 6px; margin-top: 28px; }
h2 { font-size: 15pt; color: #C40A4A; margin-top: 22px; }
h3 { font-size: 12pt; margin-top: 16px; }
table { border-collapse: collapse; width: 100%; font-size: 8.8pt; margin: 10px 0 14px; page-break-inside: auto; }
th, td { border: 1px solid #d9d9e3; padding: 4px 6px; vertical-align: top; text-align: left; }
th { background: #0B0B10; color: #fff; }
tr:nth-child(even) td { background: #fafafc; }
code { font-family: "SF Mono", Menlo, monospace; font-size: 8.8pt; background: #f3f3f7; padding: 1px 4px; border-radius: 4px; }
pre { background: #f3f3f7; padding: 10px; border-radius: 8px; font-size: 8.3pt; white-space: pre-wrap; word-break: break-word; page-break-inside: avoid; }
pre code { background: none; padding: 0; }
img { max-width: 100%; height: auto; display: block; margin: 8px auto; page-break-inside: avoid; }
blockquote { border-left: 4px solid #ED145B; margin: 10px 0; padding: 6px 12px; color: #444; background: #fff5f8; }
.mermaid { display: flex; justify-content: center; margin: 12px 0; page-break-inside: avoid; }
.mermaid svg { max-width: 100%; height: auto; }
a { color: #C40A4A; text-decoration: none; }
.cover { page-break-after: always; text-align: center; padding-top: 130px; }
.cover .logo { width: 560px; margin: 0 auto 30px; }
.cover h1 { border: none; font-size: 30pt; margin: 0 0 6px; }
.cover .sub { font-size: 13pt; color: #444; margin: 4px 0; }
.cover .meta { margin-top: 60px; font-size: 10.5pt; color: #333; line-height: 1.7; }
.cover .badge { display: inline-block; background: #ED145B; color: #fff; padding: 4px 12px; border-radius: 999px; font-weight: 700; letter-spacing: 1px; font-size: 9.5pt; margin-top: 18px; }
.annex { page-break-before: always; }
.toc { page-break-after: always; }
.toc ul { list-style: none; padding-left: 0; columns: 1; }
.toc li { margin: 3px 0; }
hr { border: none; border-top: 1px solid #ddd; margin: 18px 0; }
"""


def img_data_uri(path: Path) -> str:
    b = base64.b64encode(path.read_bytes()).decode()
    ext = path.suffix.lstrip(".").lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "svg": "image/svg+xml"}.get(ext, "application/octet-stream")
    return f"data:{mime};base64,{b}"


def convert(md_text: str, base: Path) -> str:
    # mermaid: protege os blocos antes do markdown
    blocks: list[str] = []

    def keep(m: re.Match) -> str:
        blocks.append(m.group(1))
        return f"\n\n@@MERMAID{len(blocks) - 1}@@\n\n"

    md_text = re.sub(r"```mermaid\s*\n(.*?)```", keep, md_text, flags=re.S)
    # comentários HTML de marcação → remove
    md_text = re.sub(r"<!--.*?-->", "", md_text, flags=re.S)
    html = markdown.markdown(md_text, extensions=["tables", "fenced_code", "toc", "sane_lists"])
    # imagens relativas → data URI
    def img(m: re.Match) -> str:
        src = m.group(1)
        p = (base / src).resolve()
        if p.exists() and not src.startswith(("http", "data:")):
            return f'src="{img_data_uri(p)}"'
        return m.group(0)

    html = re.sub(r'src="([^"]+)"', img, html)
    for i, code in enumerate(blocks):
        html = html.replace(f"<p>@@MERMAID{i}@@</p>", f'<div class="mermaid">{code}</div>').replace(f"@@MERMAID{i}@@", f'<div class="mermaid">{code}</div>')
    return html


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    logo = img_data_uri(DOCS / "assets" / "brand" / "asclepio-logo-horizontal.svg")
    parts = [
        f'<div class="cover"><img class="logo" src="{logo}"><h1>{DOC["title"]}</h1>'
        f'<div class="sub">Asclépio — Assistente Clínico Inteligente</div>'
        f'<div class="sub">{DOC["subtitle"]}</div>'
        f'<div class="badge">TECH CHALLENGE · FASE 3 · FIAP PÓS-TECH IA PARA DEVS (8IADT)</div>'
        f'<div class="meta">Repositório: https://github.com/rodrigogrosa/asclepio<br>Gerado em {date.today().strftime("%d/%m/%Y")}</div></div>'
    ]
    for title, path in SECTIONS:
        text = path.read_text(encoding="utf-8")
        if title:
            text = f"# {title}\n\n" + re.sub(r"^# .*\n", "", text, count=1)
        cls = ' class="annex"' if title else ""
        parts.append(f"<section{cls}>{convert(text, path.parent)}</section>")
    body = "\n".join(parts)
    html = f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><title>{DOC["title"]} — Asclépio</title>
<style>{CSS}</style>
<script type="module">
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
mermaid.initialize({{ startOnLoad: false, theme: "neutral", securityLevel: "loose", flowchart: {{ htmlLabels: true, useMaxWidth: true }} }});
await mermaid.run({{ querySelector: ".mermaid" }});
document.body.dataset.ready = "1";
</script></head><body>{body}</body></html>"""
    html_path = OUT_DIR / (DOC["out"].replace(".pdf", ".html"))
    html_path.write_text(html, encoding="utf-8")
    cmd = [CHROME, "--headless=new", "--disable-gpu", "--no-sandbox", "--run-all-compositor-stages-before-draw", "--virtual-time-budget=20000", "--no-pdf-header-footer", f"--print-to-pdf={OUT_PDF}", str(html_path)]
    subprocess.run(cmd, check=True, capture_output=True, timeout=180)
    print(json.dumps({"pdf": str(OUT_PDF), "bytes": OUT_PDF.stat().st_size}))
    html_path.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
