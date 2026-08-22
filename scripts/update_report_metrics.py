"""Atualiza as seções de resultados do relatório técnico e do README com os números reais
de ``ml/registry.json`` e ``ml/reports/eval_latest.json`` (idempotente — usa marcadores).

Uso: ``uv run python scripts/update_report_metrics.py`` (ou ``make docs-metrics``).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = json.loads((ROOT / "ml" / "registry.json").read_text(encoding="utf-8"))
EVAL = json.loads((ROOT / "ml" / "reports" / "eval_latest.json").read_text(encoding="utf-8"))
M, RAG = EVAL["models"], EVAL["rag"]
BASE, FT, REF = (
    M["base"],
    M.get("asclepio-med (ollama)", M["fine-tuned"]),
    M.get("llama3.1:8b (referência)"),
)


def pct(x: float) -> str:
    return f"{x:.0%}".replace("%", " %")


def row(name: str, v: dict) -> str:
    return (
        f"| {name} | {v['rouge_l']:.3f} | {v['bleu']:.1f} | {v['keyword_coverage']:.1%} | {v['citation_rate']:.1%} | "
        f"{v['guardrail_compliance']:.1%} | {v['safety_refusal_rate']:.0%} | {v['judge_score']:.2f} | {v['avg_latency_ms']:.0f} |"
    )


def report_section() -> str:
    rows = [
        "| Modelo | ROUGE-L | BLEU | Cobertura de termos | Taxa de citação | Conformidade guardrails | Recusa (seg.) | Juiz LLM (1–5) | Latência média (ms) |",
        "|---|---|---|---|---|---|---|---|---|",
        row("Base · Qwen2.5-0.5B-Instruct", BASE),
        row("**Fine-tuned · asclepio-med (HF merged)**", M["fine-tuned"]),
    ]
    if "asclepio-med (ollama)" in M:
        rows.append(row("**Fine-tuned · asclepio-med (Ollama)**", M["asclepio-med (ollama)"]))
    if REF:
        rows.append(row("Referência · llama3.1:8b (sem fine-tuning)", REF))
    table = "\n".join(rows)
    ref_txt = (
        f"- O juiz LLM dá nota ligeiramente maior ao fine-tuned que ao base ({BASE['judge_score']:.2f} → {FT['judge_score']:.2f}) e nota maior ao `llama3.1:8b` ({REF['judge_score']:.2f}) — um modelo 16× maior raciocina melhor, porém **cita menos, obedece menos aos guardrails ({REF['guardrail_compliance']:.0%}) e é ~{REF['avg_latency_ms'] / FT['avg_latency_ms']:.0f}× mais lento**. Isso confirma a tese: fine-tuning para forma/segurança + RAG para fatos + guardrails em código; a API permite trocar de modelo quando se quer mais raciocínio.\n"
        if REF
        else ""
    )
    return f"""<!-- ML_RESULTS_START -->
**Execução real** (`make finetune`, {REG["trained_at"][:10]}, Apple Silicon/MPS): LoRA r={REG["lora_r"]}, α={REG["lora_alpha"]}, dropout {REG.get("lora_dropout", 0.05)}, alvos {", ".join(REG.get("lora_target_modules", []))}; {REG.get("trainable_params", 0) / 1e6:.1f} M parâmetros treináveis de {REG.get("total_params", 0) / 1e6:.0f} M ({(REG.get("trainable_params", 0) / max(REG.get("total_params", 1), 1)):.1%}); {REG["epochs"]:.0f} épocas = {REG.get("global_steps", "?")} passos, batch efetivo {REG.get("effective_batch_size", "?")}, lr {REG["learning_rate"]}, seq. máx. {REG.get("max_seq_len", "?")}, {REG.get("dtype", "")}; **{REG["train_examples"]}** exemplos de treino / {REG["eval_examples"]} de validação (inclui amostras PubMedQA/MedQuAD ≤ 10 %); duração **{REG["duration_min"]} min**; loss de treino {REG["final_train_loss"]} · loss de validação {REG["final_eval_loss"]}. Exportado como safetensors → `ollama create asclepio-med` ({"ok" if REG.get("ollama_created") else "falhou"}).

![Curva de loss](assets/eval/train_loss.png)

**Avaliação** ({EVAL["generated_at"][:16]}, {BASE["n_test"]} exemplos de teste *held-out* + {BASE["n_safety"]} prompts de segurança; juiz `llama3.1:8b` em {BASE["judge_n"]} amostras):

{table}

![Comparação de métricas](assets/eval/metrics_comparison.png)
![Segurança](assets/eval/safety.png)
![Latência](assets/eval/latency.png)

**RAG** ({RAG["method"]}, {RAG["n_chunks"]} chunks, {RAG["n_queries"]} perguntas do FAQ como consultas): *hit@5* = **{RAG["hit_rate_at_5"]:.1%}**, MRR = **{RAG["mrr"]:.3f}** (baseline TF-IDF: hit@5 {RAG["tfidf_baseline"]["hit_rate_at_5"]:.1%}, MRR {RAG["tfidf_baseline"]["mrr"]:.3f}).

![RAG](assets/eval/rag.png)

**Leitura dos resultados**
- O fine-tuning **transformou o comportamento** do modelo de 0,5B: ROUGE-L {BASE["rouge_l"]:.2f} → {FT["rouge_l"]:.2f} (×{FT["rouge_l"] / BASE["rouge_l"]:.1f}), BLEU {BASE["bleu"]:.1f} → {FT["bleu"]:.1f}, cobertura de termos-chave {BASE["keyword_coverage"]:.0%} → {FT["keyword_coverage"]:.0%}, taxa de citação {BASE["citation_rate"]:.0%} → {FT["citation_rate"]:.0%}, **conformidade com os guardrails {BASE["guardrail_compliance"]:.0%} → {FT["guardrail_compliance"]:.0%}** e recusa correta no conjunto de segurança {BASE["safety_refusal_rate"]:.0%} → {FT["safety_refusal_rate"]:.0%}. Ou seja: aprendeu o formato institucional (fonte + aviso de validação), o escopo e os limites — exatamente o objetivo do fine-tuning neste projeto.
{ref_txt}- O RAG é forte (hit@5 {RAG["hit_rate_at_5"]:.0%}) e é ele quem garante os números dos protocolos nas respostas; em produção o `asclepio-med` roda com RAG, o que eleva a qualidade observada além da medida aqui (avaliação sem recuperação, só modelo).
- Limitações: conjunto de teste pequeno e gerado a partir da mesma base (risco de otimismo em ROUGE/BLEU), juiz automático em {BASE["judge_n"]} amostras, modelo pequeno ainda erra detalhes fora do que viu. Tabelas completas, amostras e análise em `docs/FINE_TUNING.md` e `ml/reports/eval_latest.md`.
<!-- ML_RESULTS_END -->"""


def readme_section() -> str:
    ref_row = (
        f"| llama3.1:8b (referência) | {REF['rouge_l']:.2f} | {REF['bleu']:.1f} | {REF['guardrail_compliance']:.0%} | {REF['safety_refusal_rate']:.0%} | {REF['avg_latency_ms'] / 1000:.1f} s |\n"
        if REF
        else ""
    )
    return f"""<!-- ML_RESULTS_START -->
Resultado real da última execução (Mac Apple Silicon, {REG["duration_min"]} min de treino, {REG["train_examples"]} exemplos, com amostras PubMedQA/MedQuAD) — avaliação em {BASE["n_test"]} perguntas *held-out* + {BASE["n_safety"]} prompts de segurança:

| Modelo | ROUGE-L | BLEU | Conformidade guardrails | Recusa correta | Latência |
|---|---|---|---|---|---|
| Base Qwen2.5-0.5B | {BASE["rouge_l"]:.2f} | {BASE["bleu"]:.1f} | {BASE["guardrail_compliance"]:.0%} | {BASE["safety_refusal_rate"]:.0%} | {BASE["avg_latency_ms"] / 1000:.1f} s |
| **asclepio-med (fine-tuned)** | **{FT["rouge_l"]:.2f}** | **{FT["bleu"]:.1f}** | **{FT["guardrail_compliance"]:.0%}** | **{FT["safety_refusal_rate"]:.0%}** | {FT["avg_latency_ms"] / 1000:.1f} s |
{ref_row}
RAG: hit@5 = {RAG["hit_rate_at_5"]:.0%}, MRR = {RAG["mrr"]:.2f}. Gráficos em `docs/assets/eval/`.
<!-- ML_RESULTS_END -->"""


def replace_block(path: Path, new: str) -> None:
    s = path.read_text(encoding="utf-8")
    pat = re.compile(r"<!-- ML_RESULTS_START -->.*?<!-- ML_RESULTS_END -->", re.DOTALL)
    if not pat.search(s):
        raise SystemExit(f"marcadores ML_RESULTS não encontrados em {path}")
    path.write_text(pat.sub(lambda _m: new, s, count=1), encoding="utf-8")
    print("atualizado", path.relative_to(ROOT))


if __name__ == "__main__":
    replace_block(ROOT / "docs" / "RELATORIO_TECNICO.md", report_section())
    replace_block(ROOT / "README.md", readme_section())
