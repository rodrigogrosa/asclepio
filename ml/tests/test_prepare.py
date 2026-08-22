"""prepare: roda ponta a ponta na mini base e verifica as garantias do dataset."""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from asclepio_core.guardrails import is_refusal
from asclepio_ml.config import load_config
from asclepio_ml.data_prep import CATEGORIES, run_prepare
from asclepio_ml.prompts import SYSTEM_PROMPT
from asclepio_ml.utils import read_jsonl

CPF = re.compile(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b")
PHONE = re.compile(r"\(\d{2}\)\s?9?\d{4}-\d{4}")


def _run(tmp_config: Path):
    cfg = load_config(tmp_config)
    out = cfg.paths.processed
    stats = run_prepare(
        cfg.paths.knowledge_base, cfg.paths.seed_instructions, out, cfg.prepare, seed=7
    )
    rows = {s: read_jsonl(out / f"{s}.jsonl") for s in ("train", "val", "test")}
    return cfg, out, stats, rows


def test_prepare_outputs_and_format(tmp_config: Path):
    cfg, out, stats, rows = _run(tmp_config)
    for name in ("train.jsonl", "val.jsonl", "test.jsonl", "dataset_stats.json", "DATASET_CARD.md"):
        assert (out / name).exists(), name
    total = sum(len(v) for v in rows.values())
    assert total == stats.total > 50
    for split_rows in rows.values():
        for r in split_rows:
            roles = [m["role"] for m in r["messages"]]
            assert roles == ["system", "user", "assistant"]
            assert r["messages"][0]["content"] == SYSTEM_PROMPT
            assert r["messages"][2]["content"].strip()
            for k in ("id", "categoria", "fontes", "origem"):
                assert k in r["meta"]
    # todas as categorias oficiais aparecem
    cats = Counter(r["meta"]["categoria"] for v in rows.values() for r in v)
    for c in CATEGORIES:
        assert cats[c] > 0, c
    # cap por categoria respeitado
    assert max(cats.values()) <= cfg.prepare["cap_per_category"]


def test_prepare_safety_guarantees(tmp_config: Path):
    _, _, _, rows = _run(tmp_config)
    all_rows = [r for v in rows.values() for r in v]
    for r in all_rows:
        cat, ans, user = (
            r["meta"]["categoria"],
            r["messages"][2]["content"],
            r["messages"][1]["content"],
        )
        if cat in {"protocolo", "documento", "paciente_contexto"}:
            assert "valida" in ans.lower()[-400:], f"sem aviso de validação: {r['meta']['id']}"
        if cat in {"recusa_prescricao", "fora_escopo"}:
            assert is_refusal(ans), f"não é recusa: {r['meta']['id']}"
        # anonimização: nenhum CPF/telefone cru sobrevive
        assert not CPF.search(ans) and not CPF.search(user), r["meta"]["id"]
        assert not PHONE.search(ans) and not PHONE.search(user), r["meta"]["id"]
    # o exemplo do seed com PII foi de fato anonimizado
    pii_rows = [
        r
        for r in all_rows
        if r["meta"]["id"].startswith("SEED-0004") or r["meta"]["id"].startswith("SEED-0011")
    ]
    assert pii_rows
    for r in pii_rows:
        txt = r["messages"][1]["content"]
        assert "[CPF]" in txt or "[PACIENTE]" in txt or "[TELEFONE]" in txt
    # resposta curta demais foi descartada
    assert not any(r["meta"]["id"].startswith("SEED-0015") for r in all_rows)


def test_prepare_split_is_grouped_and_stratified(tmp_config: Path):
    _, out, stats, rows = _run(tmp_config)
    groups = {s: {r["meta"]["group"] for r in v} for s, v in rows.items()}
    assert not (groups["train"] & groups["test"]), "paráfrases vazaram entre train e test"
    assert not (groups["train"] & groups["val"])
    assert not (groups["val"] & groups["test"])
    # proporções aproximadas
    total = stats.total
    assert 0.7 <= len(rows["train"]) / total <= 0.95
    assert len(rows["test"]) > 0 and len(rows["val"]) > 0
    st = json.loads((out / "dataset_stats.json").read_text(encoding="utf-8"))
    for k in (
        "sources",
        "generated_by_origin",
        "anonymization",
        "curation",
        "splits",
        "final_by_category",
    ):
        assert k in st
    assert st["anonymization"]["entities_removed"] >= 1
    card = (out / "DATASET_CARD.md").read_text(encoding="utf-8")
    assert "Anonimização" in card and "Splits" in card and "fictício" in card.lower()


def test_prepare_generates_from_all_sources(tmp_config: Path):
    _, _, stats, _ = _run(tmp_config)
    gen = stats.generated_by_origin
    for origin in (
        "seed",
        "faq",
        "protocolo_secao",
        "protocolo_faq",
        "protocolo_farmaco",
        "modelo",
        "paciente",
        "builtin",
    ):
        assert gen.get(origin, 0) > 0, origin
    assert stats.after_augmentation > sum(gen.values())
