from __future__ import annotations

from pathlib import Path

from asclepio_ml.plots import plot_latency, plot_metrics_comparison, plot_rag, plot_train_loss
from asclepio_ml.rag_eval import evaluate_rag


def test_rag_tfidf_on_fixture(fixture_kb: Path):
    out = evaluate_rag(fixture_kb, force_tfidf=True)
    assert out["method"] == "tfidf" and out["n_queries"] == 6
    assert 0.0 <= out["hit_rate_at_5"] <= 1.0 and 0.0 <= out["mrr"] <= 1.0
    assert out["hit_rate_at_5"] >= 0.5  # mini base: as perguntas do FAQ são próximas dos protocolos


def test_plots_write_png(tmp_path: Path):
    models = {
        "base": {
            "rouge_l": 0.2,
            "keyword_coverage": 0.3,
            "citation_rate": 0.1,
            "guardrail_compliance": 0.8,
            "judge_score": 2.5,
            "avg_latency_ms": 900,
            "bleu": 3.0,
        },
        "fine-tuned": {
            "rouge_l": 0.4,
            "keyword_coverage": 0.5,
            "citation_rate": 0.7,
            "guardrail_compliance": 0.95,
            "judge_score": None,
            "avg_latency_ms": 800,
            "bleu": 10.0,
        },
    }
    assert plot_metrics_comparison(models, tmp_path / "m.png").stat().st_size > 1000
    assert plot_latency(models, tmp_path / "l.png").exists()
    assert plot_rag(
        {"hit_rate_at_5": 0.9, "mrr": 0.7, "n_queries": 10, "method": "tfidf"}, tmp_path / "r.png"
    ).exists()
    rows = [
        {"step": 1, "loss": 2.0},
        {"step": 2, "loss": 1.5, "eval_loss": 1.6},
        {"step": 3, "loss": 1.2},
    ]
    assert plot_train_loss(rows, tmp_path / "t.png").exists()
