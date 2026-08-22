"""Gráficos (matplotlib, backend Agg) com a identidade visual do Asclépio."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

PINK = "#ED145B"
PURPLE = "#7B2FF7"
GRAY = "#9A9AAB"
DARK = "#2B2B3A"
PALETTE = [PINK, PURPLE, GRAY, "#F48FB1", "#B388FF", "#C8C8D4"]

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRAY,
        "axes.labelcolor": DARK,
        "xtick.color": DARK,
        "ytick.color": DARK,
        "text.color": DARK,
        "font.size": 11,
        "axes.titlesize": 13,
        "axes.titleweight": "bold",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
    }
)


def _save(fig: plt.Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return path


def plot_train_loss(
    log_rows: list[dict[str, Any]], path: Path, title: str = "Fine-tuning LoRA — curva de loss"
) -> Path:
    tr = [
        (r["step"], r["loss"])
        for r in log_rows
        if r.get("loss") is not None and r.get("step") is not None
    ]
    ev = [
        (r["step"], r["eval_loss"])
        for r in log_rows
        if r.get("eval_loss") is not None and r.get("step") is not None
    ]
    fig, ax = plt.subplots(figsize=(8, 4.5))
    if tr:
        ax.plot([s for s, _ in tr], [v for _, v in tr], color=PINK, lw=2, label="train loss")
    if ev:
        ax.plot(
            [s for s, _ in ev],
            [v for _, v in ev],
            color=PURPLE,
            lw=2,
            marker="o",
            ms=4,
            label="eval loss",
        )
    ax.set_xlabel("passo de otimização")
    ax.set_ylabel("loss (cross-entropy, só tokens do assistente)")
    ax.set_title(title)
    ax.grid(alpha=0.25, color=GRAY)
    ax.legend()
    return _save(fig, path)


def plot_metrics_comparison(
    models: dict[str, dict[str, Any]],
    path: Path,
    metrics: tuple[str, ...] = (
        "rouge_l",
        "keyword_coverage",
        "citation_rate",
        "guardrail_compliance",
        "judge_score_norm",
    ),
) -> Path:
    names = list(models)
    labels = {
        "rouge_l": "ROUGE-L",
        "keyword_coverage": "Cobertura de\npalavras-chave",
        "citation_rate": "Taxa de\ncitação",
        "guardrail_compliance": "Conformidade\nguardrails",
        "judge_score_norm": "LLM-juiz\n(1–5 → 0–1)",
        "bleu_norm": "BLEU/100",
    }
    fig, ax = plt.subplots(figsize=(10, 5))
    width = 0.8 / max(1, len(names))
    for i, name in enumerate(names):
        vals = []
        for m in metrics:
            if m == "judge_score_norm":
                j = models[name].get("judge_score")
                vals.append(None if j is None else (float(j) - 1) / 4)
            elif m == "bleu_norm":
                vals.append(float(models[name].get("bleu") or 0) / 100)
            else:
                vals.append(models[name].get(m))
        xs = [k + i * width for k in range(len(metrics))]
        ys = [0 if v is None else float(v) for v in vals]
        bars = ax.bar(xs, ys, width=width * 0.95, color=PALETTE[i % len(PALETTE)], label=name)
        for b, v in zip(bars, vals, strict=False):
            ax.text(
                b.get_x() + b.get_width() / 2,
                b.get_height() + 0.01,
                "n/d" if v is None else f"{float(v):.2f}",
                ha="center",
                va="bottom",
                fontsize=8,
            )
    ax.set_xticks([k + width * (len(names) - 1) / 2 for k in range(len(metrics))])
    ax.set_xticklabels([labels.get(m, m) for m in metrics])
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("valor (0–1)")
    ax.set_title("Avaliação — base × fine-tuned (quanto maior, melhor)")
    ax.legend(loc="upper left", ncol=min(3, len(names)))
    ax.grid(axis="y", alpha=0.25, color=GRAY)
    return _save(fig, path)


def plot_bleu(models: dict[str, dict[str, Any]], path: Path) -> Path:
    names = list(models)
    fig, ax = plt.subplots(figsize=(6, 4))
    vals = [float(models[n].get("bleu") or 0) for n in names]
    bars = ax.bar(names, vals, color=[PALETTE[i % len(PALETTE)] for i in range(len(names))])
    for b, v in zip(bars, vals, strict=False):
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + 0.3,
            f"{v:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylabel("BLEU (sacrebleu, corpus)")
    ax.set_title("BLEU por modelo")
    ax.grid(axis="y", alpha=0.25, color=GRAY)
    plt.setp(ax.get_xticklabels(), rotation=10, ha="right")
    return _save(fig, path)


def plot_latency(models: dict[str, dict[str, Any]], path: Path) -> Path:
    names = list(models)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    vals = [float(models[n].get("avg_latency_ms") or 0) for n in names]
    bars = ax.barh(names, vals, color=[PALETTE[i % len(PALETTE)] for i in range(len(names))])
    for b, v in zip(bars, vals, strict=False):
        ax.text(
            b.get_width() + max(vals) * 0.01,
            b.get_y() + b.get_height() / 2,
            f"{v:,.0f} ms",
            va="center",
            fontsize=9,
        )
    ax.set_xlabel("latência média por resposta (ms)")
    ax.set_title("Latência de geração")
    ax.set_xlim(0, max(vals) * 1.2 if vals and max(vals) > 0 else 1)
    ax.invert_yaxis()
    ax.grid(axis="x", alpha=0.25, color=GRAY)
    return _save(fig, path)


def plot_rag(rag: dict[str, Any], path: Path) -> Path:
    fig, ax = plt.subplots(figsize=(6, 4))
    labels = ["hit@5", "MRR"]
    vals = [float(rag.get("hit_rate_at_5") or 0), float(rag.get("mrr") or 0)]
    xs = [0, 1]
    ax.bar(
        [x - 0.18 for x in xs],
        vals,
        width=0.36,
        color=PINK,
        label=str(rag.get("method", "embeddings")),
    )
    base = rag.get("tfidf_baseline")
    if base:
        ax.bar(
            [x + 0.18 for x in xs],
            [float(base.get("hit_rate_at_5") or 0), float(base.get("mrr") or 0)],
            width=0.36,
            color=GRAY,
            label="TF-IDF (baseline)",
        )
    for x, v in zip(xs, vals, strict=False):
        ax.text(x - 0.18, v + 0.01, f"{v:.2f}", ha="center", fontsize=9)
    ax.set_xticks(xs)
    ax.set_xticklabels(labels)
    ax.set_ylim(0, 1.1)
    ax.set_title(f"RAG — recuperação do protocolo correto (n={rag.get('n_queries', 0)})")
    ax.legend()
    ax.grid(axis="y", alpha=0.25, color=GRAY)
    return _save(fig, path)


def plot_safety(models: dict[str, dict[str, Any]], path: Path) -> Path:
    names = list(models)
    fig, ax = plt.subplots(figsize=(6.5, 4))
    vals = [float(models[n].get("safety_refusal_rate") or 0) for n in names]
    bars = ax.bar(names, vals, color=[PALETTE[i % len(PALETTE)] for i in range(len(names))])
    for b, v in zip(bars, vals, strict=False):
        ax.text(
            b.get_x() + b.get_width() / 2,
            b.get_height() + 0.01,
            f"{v:.0%}",
            ha="center",
            va="bottom",
            fontsize=9,
        )
    ax.set_ylim(0, 1.12)
    ax.set_ylabel("taxa de recusa correta")
    ax.set_title("Conjunto de segurança — recusa de prescrição / fora de escopo / injeção")
    ax.grid(axis="y", alpha=0.25, color=GRAY)
    plt.setp(ax.get_xticklabels(), rotation=10, ha="right")
    return _save(fig, path)
