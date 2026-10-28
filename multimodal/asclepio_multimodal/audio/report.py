"""Artefatos da análise de áudio: gráfico de F0/intensidade e relatório em Markdown."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .features import Acoustics
from .vocal import ATENCAO, CRITICO, DISCLAIMER, SPEECH

_EVENT_COLORS = {
    "tosse": "#d62728",
    "pigarro": "#9467bd",
    "espirro": "#8c564b",
    "respiracao": "#1f77b4",
    "chiado": "#ff7f0e",
    "suspiro": "#17becf",
    "engasgo": "#e377c2",
}
_LEVEL_PT = {"normal": "normal", "atencao": "atenção", "critico": "crítico", "indisponivel": "—"}
_SENT_PT = {"positive": "positivo", "negative": "negativo", "neutral": "neutro", "mixed": "misto"}

_MEASURES = [  # (chave, rótulo, unidade)
    ("f0_mean_hz", "F0 média", "Hz"),
    ("f0_sd_st", "Variação de F0 (desvio)", "st"),
    ("f0_range_st", "Faixa de F0 (P5–P95)", "st"),
    ("jitter_local_pct", "Jitter local", "%"),
    ("shimmer_local_pct", "Shimmer local", "%"),
    ("hnr_db", "HNR", "dB"),
    ("level_dbfs", "Nível da fala", "dBFS"),
    ("voiced_fraction", "Fração vozeada", ""),
    ("phonation_ratio", "Razão de fonação", ""),
    ("n_pauses", "Pausas ≥ 250 ms", ""),
    ("pause_total_s", "Tempo em pausa", "s"),
    ("pause_mean_s", "Duração média da pausa", "s"),
    ("pauses_per_min", "Pausas por minuto", "/min"),
    ("speech_rate", "Taxa de fala", "núcleos/s"),
    ("articulation_rate", "Taxa de articulação", "núcleos/s"),
    ("breath_group_mean_s", "Grupo respiratório médio", "s"),
]


def plot_voice(ac: Acoustics, events: list[dict[str, Any]], out: Path, title: str) -> Path:
    """F0 e intensidade no tempo, com pausas sombreadas e eventos sonoros marcados."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    fig = Figure(figsize=(11, 5.2), dpi=110)
    FigureCanvasAgg(fig)
    top, bot = fig.subplots(2, 1, sharex=True)
    t = ac.series["t"]
    top.plot(
        t, [v if v is not None else float("nan") for v in ac.series["f0"]], color="#1f4e79", lw=1.4
    )
    bot.plot(t, ac.series["intensity"], color="#c55a11", lw=1.2)
    for i, (a, b) in enumerate(ac.pauses):
        for ax in (top, bot):
            ax.axvspan(
                a,
                b,
                color="#999999",
                alpha=0.25,
                label="pausa ≥ 250 ms" if i == 0 and ax is top else None,
            )
    seen = set()
    for e in events:
        lab = e["label"] if e["type"] not in seen else None
        seen.add(e["type"])
        for ax in (top, bot):
            ax.axvspan(
                e["start"],
                e["end"],
                color=_EVENT_COLORS.get(e["type"], "k"),
                alpha=0.35,
                label=lab if ax is top else None,
            )
    top.set_ylabel("F0 (Hz)")
    bot.set_ylabel("Intensidade (dB)")
    bot.set_xlabel("Tempo (s)")
    top.set_title(title, fontsize=11)
    for ax in (top, bot):
        ax.grid(alpha=0.25)
    if top.get_legend_handles_labels()[0]:
        top.legend(loc="upper right", fontsize=8, ncol=3, frameon=False)
    fig.tight_layout()
    fig.savefig(out)
    return out


def _fmt(v: Any, nd: int = 2) -> str:
    """Número em pt-BR (vírgula decimal); ``None`` vira traço."""
    if v is None:
        return "—"
    return (
        f"{v:.{nd}f}".rstrip("0").rstrip(".").replace(".", ",") if isinstance(v, float) else str(v)
    )


def mark_transcript(text: str, terms: list[dict[str, Any]]) -> str:
    """Transcrição com termos críticos em **negrito** e termos negados em _itálico (negado)_."""
    out, cur = [], 0
    for t in sorted(terms, key=lambda x: x["start"]):
        if t["start"] < cur or t["severity"] == "info":
            continue
        out.append(text[cur : t["start"]])
        piece = text[t["start"] : t["end"]]
        out.append(f"_{piece} (negado)_" if t["negated"] else f"**{piece}**")
        cur = t["end"]
    return "".join(out) + text[cur:]


def render_report(d: dict[str, Any]) -> str:
    """Relatório em Markdown a partir do dicionário montado por ``pipeline.run``."""
    lines: list[str] = [
        f"# Relatório de áudio — {d['filename']}",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Resumo",
        "",
        d["summary"],
        "",
    ]
    lines += [
        "## Indicadores vocais de triagem",
        "",
        "| Indicador | Pontuação | Nível | Motivos |",
        "|---|---|---|---|",
    ]
    for ind in d["indicators"].values():
        why = "; ".join(c["label"] for c in ind["components"] if c["z"] >= 1) or "—"
        sc = _fmt(ind["score"])
        lines.append(f"| {ind['title']} | {sc} | {_LEVEL_PT[ind['level']]} | {why} |")
    lines += [
        "",
        f"Limiares: atenção ≥ {_fmt(ATENCAO)}, crítico ≥ {_fmt(CRITICO)}. Pontuação 0 = dentro da referência "
        "de falantes sem queixa (ver `vocal.py`).",
        "",
    ]
    lines += [
        "## Medidas da voz e da fala",
        "",
        "| Medida | Valor | Referência (mediana) |",
        "|---|---|---|",
    ]
    for key, label, unit in _MEASURES:
        v = d["features"].get(key)
        ref = SPEECH.get(key)
        lines.append(
            f"| {label} | {_fmt(v)} {unit} | {_fmt(ref.median) + ' ' + ref.unit if ref else '—'} |".replace(
                "  |", " |"
            )
        )
    lines.append("")
    lines += ["## Transcrição", ""]
    if d["transcript"]:
        lines += [
            mark_transcript(d["transcript"], d["critical_terms"]),
            "",
            "Legenda: **termo crítico**; _termo negado pelo paciente_.",
            "",
        ]
    else:
        lines += ["Sem transcrição (veja os avisos).", ""]
    if d["critical_terms"]:
        lines += [
            "## Termos críticos",
            "",
            "| Trecho | Categoria | Severidade | Negado | Fonte |",
            "|---|---|---|---|---|",
        ]
        for t in d["critical_terms"]:
            lines.append(
                f"| {t['text']} | {t['category']} | {t['severity']} | {'sim' if t['negated'] else 'não'} | {t['source']} |"
            )
        lines.append("")
    s = d["sentiment"]
    if s:
        sc = s["scores"]
        lines += [
            "## Sentimento",
            "",
            f"Geral: **{_SENT_PT.get(s['overall'], s['overall'])}** "
            f"(positivo {_fmt(sc['positive'])} · neutro {_fmt(sc['neutral'])} · negativo {_fmt(sc['negative'])}).",
            "",
        ]
    if d["key_phrases"]:
        lines += ["## Frases-chave (Azure)", "", ", ".join(d["key_phrases"]), ""]
    if d["health_entities"]:
        lines += [
            "## Entidades de saúde (Azure Text Analytics for Health)",
            "",
            "| Entidade | Categoria | Negada | Severidade |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {e['text']} | {e['category']} | {'sim' if e['negated'] else 'não'} | {e['severity']} |"
            for e in d["health_entities"]
        ]
        lines.append("")
    ev = d["audio_events"]
    lines += ["## Eventos sonoros (AST / AudioSet)", ""]
    if ev.get("events"):
        lines += ["| Evento | Início (s) | Fim (s) | Probabilidade |", "|---|---|---|---|"]
        lines += [
            f"| {e['label']} | {_fmt(e['start'], 1)} | {_fmt(e['end'], 1)} | {_fmt(e['score'])} |"
            for e in ev["events"]
        ]
    else:
        lines.append(ev.get("reason") or "Nenhum evento acima do limiar.")
    lines += ["", "## Provedores e modelos", ""]
    lines += [f"- {m['name']} ({m['provider']}) — {m['task']}" for m in d["models"]]
    lines.append(f"- Dados pessoais mascarados antes do envio ao Azure: {d['pii_masked']}")
    if d["warnings"]:
        lines += ["", "## Avisos", ""] + [f"- {w}" for w in d["warnings"]]
    return "\n".join(lines) + "\n"
