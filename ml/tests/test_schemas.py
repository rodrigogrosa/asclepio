from __future__ import annotations

import json
from pathlib import Path

import pytest
from asclepio_ml.registry import (
    FINETUNE_META_FIELDS,
    build_finetune_meta,
    read_registry,
    validate_eval_report,
    validate_finetune_meta,
    write_registry,
)


def _meta():
    return build_finetune_meta(
        run_id="r1",
        base_model="Qwen/Qwen2.5-0.5B-Instruct",
        epochs=2,
        train_examples=100,
        eval_examples=10,
        final_train_loss=1.234,
        final_eval_loss=1.1,
        lora_r=16,
        lora_alpha=32,
        learning_rate=2e-4,
        duration_min=12.5,
        device="mps",
        max_seq_len=1024,
    )


def test_finetune_meta_schema(tmp_path: Path):
    meta = _meta()
    assert validate_finetune_meta(meta) == []
    assert meta["method"] == "LoRA" and meta["ollama_model"] == "asclepio-med"
    assert set(FINETUNE_META_FIELDS) <= set(meta)
    write_registry(tmp_path / "registry.json", meta)
    back = read_registry(tmp_path / "registry.json")
    assert back == json.loads(json.dumps(meta))
    del meta["device"]
    assert validate_finetune_meta(meta) == ["device"]
    with pytest.raises(ValueError):
        write_registry(tmp_path / "x.json", meta)


def test_eval_report_schema():
    good = {
        "generated_at": "2026-01-01T00:00:00",
        "models": {
            "base": {
                "rouge_l": 0.1,
                "bleu": 1.0,
                "keyword_coverage": 0.2,
                "citation_rate": 0.0,
                "judge_score": None,
                "guardrail_compliance": 0.9,
                "avg_latency_ms": 100,
                "n": 3,
            }
        },
        "rag": {"hit_rate_at_5": 0.8, "mrr": 0.6, "n_queries": 10},
        "per_sample": [
            {
                "id": "a",
                "categoria": "protocolo",
                "prompt": "p",
                "reference": "r",
                "outputs": {"base": "o"},
                "scores": {"base": {}},
            }
        ],
    }
    assert validate_eval_report(good) == []
    bad = {
        "generated_at": "x",
        "models": {"m": {"rouge_l": 1}},
        "rag": {},
        "per_sample": [{"id": 1}],
    }
    probs = validate_eval_report(bad)
    assert (
        any("models['m']" in p for p in probs)
        and any("rag" in p for p in probs)
        and any("per_sample" in p for p in probs)
    )
