"""Etapa ``evaluate`` — compara modelo base × fine-tuned (× referência) e mede o RAG.

Conjuntos:
- ``test.jsonl`` (amostra estratificada, ``--max-samples``): métricas de qualidade vs referência.
- **conjunto de segurança**: prompts adversariais fixos (``prompts.SAFETY_PROMPTS``) + exemplos de
  recusa do próprio test — aqui o que importa é *recusar* (``is_refusal``) e não prescrever.

Modelos:
- ``base``: modelo base via transformers (mesmo system prompt).
- ``fine-tuned``: modelo fundido (``ml/models/asclepio-med``) via transformers — ou o adapter.
- ``asclepio-med (ollama)``: opcional, o artefato final realmente usado pelo backend.
- ``llama3.1:8b (referência)``: opcional (``--include-reference``), um modelo 16x maior sem
  fine-tuning, para contextualizar os números.

Saídas: ``ml/reports/eval_latest.json`` (esquema ``EvalReport``), ``eval_latest.md`` e PNGs.
"""

from __future__ import annotations

import gc
import random
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from asclepio_core.guardrails import is_refusal
from asclepio_core.knowledge import load_knowledge_base

from asclepio_ml import prompts
from asclepio_ml.config import Config
from asclepio_ml.metrics import SampleScore, aggregate, build_drug_lexicon, score_sample
from asclepio_ml.plots import (
    plot_bleu,
    plot_latency,
    plot_metrics_comparison,
    plot_rag,
    plot_safety,
)
from asclepio_ml.rag_eval import evaluate_rag
from asclepio_ml.registry import read_registry, validate_eval_report
from asclepio_ml.utils import batched, get_device, log, read_jsonl, resolve_dtype, write_json

REFUSAL_CATEGORIES = {"recusa_prescricao", "fora_escopo", "injecao"}


# ---------------------------------------------------------------------------
# Geradores
# ---------------------------------------------------------------------------
class HFGenerator:
    """Geração em lote com transformers (greedy, padding à esquerda)."""

    def __init__(
        self,
        model_path: str,
        device: str,
        max_new_tokens: int = 256,
        batch_size: int = 8,
        dtype: str = "auto",
    ) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = device
        self.max_new_tokens = max_new_tokens
        self.batch_size = batch_size
        self.tok = AutoTokenizer.from_pretrained(model_path)
        self.tok.padding_side = "left"
        if self.tok.pad_token is None:
            self.tok.pad_token = self.tok.eos_token
        # fp32 em MPS/CPU por segurança numérica (fp16 em MPS pode gerar NaN em alguns modelos)
        self.model = (
            AutoModelForCausalLM.from_pretrained(model_path, dtype=resolve_dtype(device, dtype))
            .to(device)
            .eval()
        )
        self.torch = torch

    def generate(self, conversations: list[list[dict[str, str]]]) -> list[tuple[str, float]]:
        out: list[tuple[str, float]] = []
        for batch in batched(conversations, self.batch_size):
            texts = [
                self.tok.apply_chat_template(c, tokenize=False, add_generation_prompt=True)
                for c in batch
            ]
            enc = self.tok(
                texts, return_tensors="pt", padding=True, truncation=True, max_length=3072
            ).to(self.device)
            t0 = time.time()
            with self.torch.no_grad():
                gen = self.model.generate(
                    **enc,
                    max_new_tokens=self.max_new_tokens,
                    do_sample=False,
                    pad_token_id=self.tok.pad_token_id,
                    repetition_penalty=1.05,
                )
            dt = (time.time() - t0) * 1000 / len(batch)
            new = gen[:, enc["input_ids"].shape[1] :]
            for row in new:
                out.append((self.tok.decode(row, skip_special_tokens=True).strip(), dt))
            log(f"  … {len(out)}/{len(conversations)} respostas geradas")
        return out

    def close(self) -> None:
        del self.model
        gc.collect()
        if self.device == "mps":
            self.torch.mps.empty_cache()
        elif self.device == "cuda":
            self.torch.cuda.empty_cache()


class OllamaGenerator:
    def __init__(self, model: str, base_url: str, max_new_tokens: int = 256) -> None:
        from langchain_ollama import ChatOllama

        self.model = model
        self.llm = ChatOllama(
            model=model, base_url=base_url, temperature=0, num_predict=max_new_tokens
        )

    def generate(self, conversations: list[list[dict[str, str]]]) -> list[tuple[str, float]]:
        from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

        out: list[tuple[str, float]] = []
        for i, conv in enumerate(conversations, 1):
            msgs = []
            for m in conv:
                cls = {"system": SystemMessage, "user": HumanMessage, "assistant": AIMessage}[
                    m["role"]
                ]
                msgs.append(cls(content=m["content"]))
            t0 = time.time()
            try:
                text = str(self.llm.invoke(msgs).content)
            except Exception as exc:
                text = f"[erro ollama: {exc}]"
            out.append((text.strip(), (time.time() - t0) * 1000))
            if i % 10 == 0:
                log(f"  … {i}/{len(conversations)} respostas ({self.model})")
        return out

    def close(self) -> None:
        return None


def ollama_models(base_url: str) -> list[str]:
    try:
        import httpx

        r = httpx.get(f"{base_url}/api/tags", timeout=5)
        r.raise_for_status()
        return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []


def _has_model(names: list[str], wanted: str) -> bool:
    w = wanted.split(":")[0]
    return any(
        n == wanted or n == f"{wanted}:latest" or (n.split(":")[0] == w and (":" not in wanted))
        for n in names
    )


# ---------------------------------------------------------------------------
# LLM-juiz
# ---------------------------------------------------------------------------
def judge_scores(
    items: list[dict[str, Any]],
    outputs: dict[str, list[str]],
    judge_model: str,
    base_url: str,
    limit: int,
) -> dict[str, list[int | None]]:
    """Nota 1-5 por (item, modelo) nos primeiros ``limit`` itens com referência."""
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_ollama import ChatOllama

    llm = ChatOllama(model=judge_model, base_url=base_url, temperature=0, num_predict=8)
    res: dict[str, list[int | None]] = {m: [None] * len(items) for m in outputs}
    idxs = [i for i, it in enumerate(items) if it.get("reference")][:limit]
    total = len(idxs) * len(outputs)
    done = 0
    for i in idxs:
        it = items[i]
        for m, outs in outputs.items():
            msg = prompts.JUDGE_USER.format(
                pergunta=it["prompt"][:2500],
                referencia=it["reference"][:2500],
                resposta=(outs[i] or "")[:2500],
            )
            try:
                ans = str(
                    llm.invoke(
                        [SystemMessage(content=prompts.JUDGE_SYSTEM), HumanMessage(content=msg)]
                    ).content
                )
                mm = re.search(r"[1-5]", ans)
                res[m][i] = int(mm.group(0)) if mm else None
            except Exception as exc:
                log(f"[yellow]juiz falhou no item {it['id']}/{m}: {exc}[/]")
                res[m][i] = None
            done += 1
            if done % 20 == 0:
                log(f"  … juiz {done}/{total}")
    return res


# ---------------------------------------------------------------------------
# Relatório markdown
# ---------------------------------------------------------------------------
def render_markdown(report: dict[str, Any], meta: dict[str, Any]) -> str:
    models = report["models"]
    cols = [
        "rouge_l",
        "bleu",
        "keyword_coverage",
        "citation_rate",
        "guardrail_compliance",
        "safety_refusal_rate",
        "judge_score",
        "avg_latency_ms",
        "n",
    ]
    head = "| modelo | ROUGE-L | BLEU | cobertura kw | citação | guardrails | recusa segura | juiz (1-5) | latência (ms) | n |\n|---|---|---|---|---|---|---|---|---|---|"
    rows = []
    for name, m in models.items():
        vals = []
        for c in cols:
            v = m.get(c)
            if v is None:
                vals.append("n/d")
            elif c in {"bleu", "avg_latency_ms"}:
                vals.append(f"{v:.1f}" if c == "bleu" else f"{v:,.0f}")
            elif c == "n":
                vals.append(str(v))
            elif c == "judge_score":
                vals.append(f"{v:.2f}")
            else:
                vals.append(f"{v:.3f}")
        rows.append(f"| **{name}** | " + " | ".join(vals) + " |")
    rag = report["rag"]
    base = models.get("base", {})
    ft = models.get("fine-tuned", {})

    def delta(k: str) -> str:
        a, b = base.get(k), ft.get(k)
        if a is None or b is None:
            return "n/d"
        return f"{b - a:+.3f}"

    analysis = [
        f"- ROUGE-L: {delta('rouge_l')} · cobertura de palavras-chave: {delta('keyword_coverage')} · taxa de citação: {delta('citation_rate')} (fine-tuned − base).",
        f"- Guardrails: {delta('guardrail_compliance')} · recusa segura: {delta('safety_refusal_rate')} · juiz: {delta('judge_score')}.",
        "- Leitura: o fine-tuning ensina *formato institucional* (citar PROT-/MOD-, aviso de validação, recusar prescrição) — é isso que as métricas de citação/guardrails capturam; ROUGE/BLEU medem sobreposição lexical com a resposta de referência e sobem quando o modelo reproduz a terminologia dos protocolos.",
        "- Limitações: referências únicas (uma resposta 'correta' por pergunta), modelo base de 0,5 B parâmetros, avaliação automática + LLM-juiz (não substitui validação clínica humana).",
    ]
    return f"""# Avaliação — Asclépio (fine-tuning LoRA)

Gerado em {report["generated_at"]} · run `{meta.get("run_id", "n/d")}` · base `{meta.get("base_model", "n/d")}` · device `{meta.get("device", "n/d")}`

## Modelos (conjunto de teste: {meta.get("n_test", "n/d")} amostras · segurança: {meta.get("n_safety", "n/d")} prompts)
{head}
{chr(10).join(rows)}

> `guardrails` = % de respostas sem linguagem prescritiva imperativa e sem PII (+ recusa correta no conjunto de segurança).
> `recusa segura` = % de recusas corretas apenas no conjunto de segurança. `juiz` = LLM-juiz `{meta.get("judge_model", "n/d")}` (amostra de {meta.get("judge_limit", "n/d")} itens).

## RAG (perguntas do FAQ → protocolo correto)
| método | hit@5 | MRR | consultas | chunks |
|---|---|---|---|---|
| {rag.get("method", "n/d")} | {rag.get("hit_rate_at_5", 0):.3f} | {rag.get("mrr", 0):.3f} | {rag.get("n_queries", 0)} | {rag.get("n_chunks", "n/d")} |
{("| TF-IDF (baseline) | " + f"{rag['tfidf_baseline']['hit_rate_at_5']:.3f} | {rag['tfidf_baseline']['mrr']:.3f} | {rag.get('n_queries', 0)} | {rag.get('n_chunks', 'n/d')} |") if rag.get("tfidf_baseline") else ""}

## Análise curta
{chr(10).join(analysis)}

## Gráficos
![métricas](../../docs/assets/eval/metrics_comparison.png)
![latência](../../docs/assets/eval/latency.png)
![segurança](../../docs/assets/eval/safety.png)
![rag](../../docs/assets/eval/rag.png)
![loss](../../docs/assets/eval/train_loss.png)
"""


# ---------------------------------------------------------------------------
# Orquestração
# ---------------------------------------------------------------------------
def _sample_test(rows: list[dict[str, Any]], max_samples: int, seed: int) -> list[dict[str, Any]]:
    """Amostra estratificada (round-robin por categoria) do test.jsonl."""
    rng = random.Random(seed)
    by_cat: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_cat[r.get("meta", {}).get("categoria", "outros")].append(r)
    for v in by_cat.values():
        rng.shuffle(v)
    out: list[dict[str, Any]] = []
    cats = sorted(by_cat)
    while len(out) < max_samples and any(by_cat[c] for c in cats):
        for c in cats:
            if by_cat[c] and len(out) < max_samples:
                out.append(by_cat[c].pop())
    return out


def run_evaluate(
    cfg: Config,
    *,
    max_samples: int | None = None,
    include_reference: bool = False,
    use_judge: bool = True,
    include_ollama_finetuned: bool = True,
    base_model: str | None = None,
    merged_path: Path | None = None,
    output_dir: Path | None = None,
    device: str | None = None,
    skip_base: bool = False,
    skip_finetuned: bool = False,
    force_tfidf: bool = False,
) -> dict[str, Any]:
    ev = cfg.evaluate
    seed = cfg.seed
    base_url = str(ev.get("ollama_base_url", "http://localhost:11434"))
    max_samples = int(max_samples or ev.get("max_samples", 120))
    per_sample_limit = int(ev.get("per_sample_limit", 60))
    max_new = int(ev.get("max_new_tokens", 256))
    batch_size = int(ev.get("batch_size", 8))
    reg = read_registry(cfg.paths.registry) or {}
    base_model = base_model or reg.get("base_model") or cfg.base_model
    ollama_name = str(reg.get("ollama_model") or cfg.export.get("ollama_model", "asclepio-med"))
    merged_path = merged_path or (
        cfg.root / reg["merged_path"] if reg.get("merged_path") else cfg.paths.models / ollama_name
    )
    adapter_path = cfg.root / reg["adapter_path"] if reg.get("adapter_path") else None
    out_dir = output_dir or cfg.paths.reports
    device = get_device(device)

    # --- itens ------------------------------------------------------------------------------
    test_rows = read_jsonl(cfg.paths.processed / "test.jsonl")
    if not test_rows:
        raise FileNotFoundError("test.jsonl não encontrado — rode 'prepare'.")
    sample = _sample_test(test_rows, max_samples, seed)
    items: list[dict[str, Any]] = []
    for r in sample:
        msgs = r["messages"]
        cat = r.get("meta", {}).get("categoria", "outros")
        items.append(
            {
                "id": r["meta"].get("id"),
                "categoria": cat,
                "messages": msgs[:-1],
                "prompt": msgs[-2]["content"],
                "reference": msgs[-1]["content"],
                "expect_refusal": cat in REFUSAL_CATEGORIES,
                "set": "test",
            }
        )
    for s in prompts.SAFETY_PROMPTS:
        items.append(
            {
                "id": s["id"],
                "categoria": s["categoria"],
                "messages": [
                    {"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": s["prompt"]},
                ],
                "prompt": s["prompt"],
                "reference": None,
                "expect_refusal": True,
                "set": "safety",
            }
        )
    n_test = sum(1 for it in items if it["set"] == "test")
    n_safety = len(items) - n_test
    log(f"itens: {n_test} de teste + {n_safety} de segurança · device={device}")

    # --- modelos ------------------------------------------------------------------------------
    available = ollama_models(base_url)
    generators: dict[str, Any] = {}
    if not skip_base:
        generators["base"] = ("hf", base_model)
    if not skip_finetuned:
        if (
            merged_path
            and Path(merged_path).exists()
            and any(Path(merged_path).glob("*.safetensors"))
        ):
            generators["fine-tuned"] = ("hf", str(merged_path))
        elif adapter_path and adapter_path.exists():
            generators["fine-tuned"] = ("hf-adapter", str(adapter_path))
        else:
            log(
                "[yellow]modelo fine-tuned não encontrado (rode train/export) — avaliando só o base.[/]"
            )
    if include_ollama_finetuned and _has_model(available, ollama_name):
        generators[f"{ollama_name} (ollama)"] = ("ollama", ollama_name)
    ref_model = str(ev.get("reference_model", "llama3.1:8b"))
    if include_reference:
        if _has_model(available, ref_model):
            generators[f"{ref_model} (referência)"] = ("ollama", ref_model)
        else:
            log(f"[yellow]modelo de referência {ref_model} não está no Ollama — ignorado.[/]")

    convs = [it["messages"] for it in items]
    outputs: dict[str, list[str]] = {}
    latencies: dict[str, list[float]] = {}
    for name, (kind, target) in generators.items():
        log(f"[bold]gerando com {name}[/] ({kind}: {target})")
        t0 = time.time()
        if kind == "hf":
            gen = HFGenerator(target, device, max_new, batch_size)
        elif kind == "hf-adapter":
            gen = HFGenerator(base_model, device, max_new, batch_size)
            from peft import PeftModel

            gen.model = PeftModel.from_pretrained(gen.model, target).merge_and_unload().eval()
        else:
            gen = OllamaGenerator(target, base_url, max_new)
        res = gen.generate(convs)
        gen.close()
        outputs[name] = [r[0] for r in res]
        latencies[name] = [r[1] for r in res]
        log(f"{name}: {len(res)} respostas em {(time.time() - t0) / 60:.1f} min")

    # --- métricas -----------------------------------------------------------------------------
    lexicon = build_drug_lexicon(load_knowledge_base(cfg.paths.knowledge_base))
    scores: dict[str, list[SampleScore]] = {}
    for name, outs in outputs.items():
        scores[name] = [
            score_sample(
                it["reference"],
                o,
                expect_refusal=it["expect_refusal"],
                lexicon=lexicon,
                latency_ms=lat,
            )
            for it, o, lat in zip(items, outs, latencies[name], strict=False)
        ]

    judge_model = str(ev.get("judge_model", "llama3.1:8b"))
    judge_used = False
    if use_judge and outputs:
        if _has_model(available, judge_model):
            log(
                f"[bold]LLM-juiz[/] {judge_model} em até {per_sample_limit} itens × {len(outputs)} modelos"
            )
            js = judge_scores(items, outputs, judge_model, base_url, per_sample_limit)
            for name, arr in js.items():
                for s, j in zip(scores[name], arr, strict=False):
                    s.judge_score = j
            judge_used = True
        else:
            log(f"[yellow]Ollama/juiz {judge_model} indisponível — judge_score = null.[/]")

    models_report: dict[str, dict[str, Any]] = {}
    for name, sc in scores.items():
        agg = aggregate(sc, [it["reference"] for it in items], outputs[name])
        safety_idx = [i for i, it in enumerate(items) if it["set"] == "safety"]
        agg["safety_refusal_rate"] = round(
            sum(1 for i in safety_idx if is_refusal(outputs[name][i])) / max(1, len(safety_idx)), 4
        )
        agg["n_test"] = n_test
        agg["n_safety"] = n_safety
        models_report[name] = agg

    # --- RAG ------------------------------------------------------------------------------------
    log("[bold]RAG[/] hit@5 / MRR")
    rag = evaluate_rag(
        cfg.paths.knowledge_base,
        str(ev.get("embed_model", "nomic-embed-text")),
        base_url,
        force_tfidf=force_tfidf,
    )
    log(f"RAG: {rag}")

    # --- per_sample ---------------------------------------------------------------------------------
    per_sample: list[dict[str, Any]] = []
    for i, it in enumerate(items[:per_sample_limit]):
        per_sample.append(
            {
                "id": it["id"],
                "categoria": it["categoria"],
                "prompt": it["prompt"],
                "reference": it["reference"],
                "outputs": {name: outputs[name][i] for name in outputs},
                "scores": {name: scores[name][i].as_dict() for name in outputs},
            }
        )

    report: dict[str, Any] = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "models": models_report,
        "rag": rag,
        "per_sample": per_sample,
        "meta": {
            "run_id": reg.get("run_id"),
            "base_model": base_model,
            "device": device,
            "n_test": n_test,
            "n_safety": n_safety,
            "judge_model": judge_model if judge_used else None,
            "judge_limit": per_sample_limit,
            "max_new_tokens": max_new,
            "generators": dict(generators),
        },
    }
    problems = validate_eval_report(report)
    if problems:
        raise ValueError(f"EvalReport inválido: {problems}")

    out_dir.mkdir(parents=True, exist_ok=True)
    write_json(out_dir / "eval_latest.json", report)
    (out_dir / "eval_latest.md").write_text(
        render_markdown(report, report["meta"]), encoding="utf-8"
    )
    assets = cfg.paths.assets
    if models_report:
        plot_metrics_comparison(models_report, assets / "metrics_comparison.png")
        plot_bleu(models_report, assets / "bleu.png")
        plot_latency(models_report, assets / "latency.png")
        plot_safety(models_report, assets / "safety.png")
    plot_rag(rag, assets / "rag.png")
    log(
        f"relatório → {out_dir / 'eval_latest.json'} · {out_dir / 'eval_latest.md'} · gráficos → {assets}"
    )
    return report
