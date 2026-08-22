"""CLI do pipeline: ``uv run python -m asclepio_ml <comando>``.

Comandos: ``prepare`` · ``train`` · ``export`` · ``evaluate`` · ``all`` · ``synthetic-patients``.
"""

from __future__ import annotations

import os
from pathlib import Path

# Antes de importar torch: permite que operações sem kernel MPS caiam para CPU em vez de falhar.
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Limita o cache do alocador MPS a ~70 % da memória recomendada da GPU integrada: sem isso o
# PyTorch (ratio padrão 1.7) continua alocando além da RAM física e o macOS entra em swap.
os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.7")
os.environ.setdefault("PYTORCH_MPS_LOW_WATERMARK_RATIO", "0.5")  # deve ser ≤ HIGH (padrão 1.4)

import typer

from asclepio_ml.config import DEFAULT_CONFIG_PATH, load_config
from asclepio_ml.utils import log

app = typer.Typer(
    help="Asclépio · pipeline de fine-tuning e avaliação (LoRA, Ollama, métricas).",
    no_args_is_help=True,
    add_completion=False,
)

ConfigOpt = typer.Option(
    DEFAULT_CONFIG_PATH, "--config", "-c", help="Arquivo YAML de configuração."
)
ProfileOpt = typer.Option(
    "full", "--profile", "-p", help="Perfil de treino: quick (smoke) ou full."
)
BaseModelOpt = typer.Option(
    None, "--base-model", "-m", help="Modelo base HF (ex.: Qwen/Qwen2.5-0.5B-Instruct)."
)


@app.command()
def prepare(
    config: Path = ConfigOpt,
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Diretório de saída (padrão: data/processed)."
    ),
    with_public: bool = typer.Option(
        False, "--with-public", help="Mistura ≤10% de PubMedQA/MedQuAD (requer rede)."
    ),
    seed: int | None = typer.Option(None, "--seed", help="Semente (padrão: a do YAML)."),
) -> None:
    """Monta o dataset: carrega → gera → augmenta → anonimiza → cura → divide."""
    from asclepio_ml.data_prep import run_prepare

    cfg = load_config(config)
    out = output or cfg.paths.processed
    st = run_prepare(
        cfg.paths.knowledge_base,
        cfg.paths.seed_instructions,
        out,
        cfg.prepare,
        seed=seed or cfg.seed,
        with_public=with_public,
    )
    log(f"[green]prepare concluído:[/] {st.total} exemplos · {st.splits}")


@app.command()
def train(
    config: Path = ConfigOpt,
    profile: str = ProfileOpt,
    base_model: str | None = BaseModelOpt,
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Diretório dos runs (padrão: ml/runs)."
    ),
    device: str | None = typer.Option(None, "--device", help="cuda | mps | cpu (padrão: auto)."),
    max_train_examples: int | None = typer.Option(
        None, "--max-train-examples", help="Limita exemplos (debug)."
    ),
    run_id: str | None = typer.Option(
        None, "--run-id", help="Nome do run (padrão: timestamp-perfil)."
    ),
) -> None:
    """Fine-tuning LoRA (PEFT + TRL SFTTrainer)."""
    from asclepio_ml.train import run_train

    cfg = load_config(config)
    meta = run_train(
        cfg,
        cfg.profile(profile),
        base_model=base_model,
        output_dir=output,
        device=device,
        max_train_examples=max_train_examples,
        run_id=run_id,
    )
    log(
        f"[green]train concluído:[/] run {meta['run_id']} · loss {meta['final_train_loss']} · eval {meta['final_eval_loss']} · {meta['duration_min']} min"
    )


@app.command()
def export(
    config: Path = ConfigOpt,
    run_id: str | None = typer.Option(
        None, "--run-id", help="Run a exportar (padrão: o do registry)."
    ),
    base_model: str | None = BaseModelOpt,
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Diretório do modelo fundido (padrão: ml/models/asclepio-med)."
    ),
    name: str | None = typer.Option(
        None, "--name", help="Nome do modelo no Ollama (padrão: asclepio-med)."
    ),
    no_ollama: bool = typer.Option(
        False, "--no-ollama", help="Só funde e gera Modelfile; não chama o Ollama."
    ),
    gguf: bool = typer.Option(
        False, "--gguf", help="Força conversão GGUF (llama.cpp) em vez de importar safetensors."
    ),
) -> None:
    """Funde o adapter no base, gera Modelfile e cria o modelo no Ollama."""
    from asclepio_ml.export import run_export

    cfg = load_config(config)
    rep = run_export(
        cfg,
        run_id=run_id,
        base_model=base_model,
        output_dir=output,
        ollama_name=name,
        create=not no_ollama,
        force_gguf=gguf,
    )
    log(
        f"[green]export concluído:[/] {rep.get('merged_path')} · ollama_created={rep.get('ollama_created')} · método={rep.get('export_method')}"
    )


@app.command()
def evaluate(
    config: Path = ConfigOpt,
    max_samples: int | None = typer.Option(
        None, "--max-samples", help="Amostra do test.jsonl (padrão: YAML)."
    ),
    include_reference: bool = typer.Option(
        False, "--include-reference", help="Inclui llama3.1:8b (Ollama) como referência."
    ),
    no_judge: bool = typer.Option(False, "--no-judge", help="Desliga o LLM-juiz."),
    no_ollama_finetuned: bool = typer.Option(
        False, "--no-ollama-finetuned", help="Não avalia o asclepio-med via Ollama."
    ),
    base_model: str | None = BaseModelOpt,
    merged_path: Path | None = typer.Option(
        None, "--merged-path", help="Diretório do modelo fundido."
    ),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Diretório dos relatórios (padrão: ml/reports)."
    ),
    device: str | None = typer.Option(None, "--device"),
    skip_base: bool = typer.Option(False, "--skip-base"),
    skip_finetuned: bool = typer.Option(False, "--skip-finetuned"),
    tfidf: bool = typer.Option(False, "--tfidf", help="Força TF-IDF no RAG (sem Ollama)."),
) -> None:
    """Avalia base × fine-tuned (× referência) + RAG; gera JSON/MD/PNG."""
    from asclepio_ml.evaluate import run_evaluate

    cfg = load_config(config)
    rep = run_evaluate(
        cfg,
        max_samples=max_samples,
        include_reference=include_reference,
        use_judge=not no_judge,
        include_ollama_finetuned=not no_ollama_finetuned,
        base_model=base_model,
        merged_path=merged_path,
        output_dir=output,
        device=device,
        skip_base=skip_base,
        skip_finetuned=skip_finetuned,
        force_tfidf=tfidf,
    )
    for name, m in rep["models"].items():
        log(
            f"  {name}: rouge_l={m['rouge_l']} kw={m['keyword_coverage']} cit={m['citation_rate']} guard={m['guardrail_compliance']} judge={m['judge_score']} lat={m['avg_latency_ms']}ms"
        )
    log(
        f"[green]evaluate concluído.[/] RAG hit@5={rep['rag']['hit_rate_at_5']} mrr={rep['rag']['mrr']}"
    )


@app.command("all")
def run_all(
    config: Path = ConfigOpt,
    profile: str = ProfileOpt,
    base_model: str | None = BaseModelOpt,
    include_reference: bool = typer.Option(False, "--include-reference"),
    max_samples: int | None = typer.Option(None, "--max-samples"),
    no_ollama: bool = typer.Option(
        False, "--no-ollama", help="Pula criação no Ollama e juiz/referência."
    ),
) -> None:
    """prepare → train → export → evaluate."""
    from asclepio_ml.data_prep import run_prepare
    from asclepio_ml.evaluate import run_evaluate
    from asclepio_ml.export import run_export
    from asclepio_ml.train import run_train

    cfg = load_config(config)
    run_prepare(
        cfg.paths.knowledge_base,
        cfg.paths.seed_instructions,
        cfg.paths.processed,
        cfg.prepare,
        seed=cfg.seed,
    )
    meta = run_train(cfg, cfg.profile(profile), base_model=base_model)
    run_export(cfg, run_id=meta["run_id"], base_model=base_model, create=not no_ollama)
    run_evaluate(
        cfg,
        max_samples=max_samples,
        include_reference=include_reference and not no_ollama,
        use_judge=not no_ollama,
        include_ollama_finetuned=not no_ollama,
        base_model=base_model,
    )
    log("[green]pipeline completo.[/]")


@app.command("synthetic-patients")
def synthetic_patients(
    output: Path = typer.Option(Path("data/synthetic/patients.json"), "--output", "-o"),
) -> None:
    """Gera data/synthetic/patients.json (pacientes fictícios via asclepio_core.synthetic)."""
    from asclepio_core.synthetic import write_patients

    n = write_patients(output)
    log(f"[green]{n} pacientes sintéticos gravados em {output}[/]")


if __name__ == "__main__":
    app()
