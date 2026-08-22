"""Etapa ``train`` — fine-tuning supervisionado (SFT) com LoRA.

**O que é LoRA?** Em vez de atualizar os bilhões de pesos do modelo, congelamos o modelo base
e treinamos duas matrizes pequenas (A: d×r, B: r×d, com r ≪ d) somadas a cada projeção
escolhida (q/k/v/o/gate/up/down). Com r=16 treinamos ~1-2 % dos parâmetros, o que cabe em
memória de um laptop, converge rápido e produz um *adapter* de poucos MB que pode ser
fundido ao modelo base na exportação.

**Por que TRL SFTTrainer?** Ele já aplica o *chat template* do modelo base, calcula a
loss apenas nos tokens do assistente (formato prompt/completion → ``completion_only_loss``)
e integra PEFT — menos código manual, menos bug. Se a versão instalada não suportar esse
formato, o código cai em ``assistant_only_loss``/texto simples (ver ``_build_dataset``).

Saídas: ``ml/runs/<run_id>/adapter``, ``trainer_state.json``, ``train_log.jsonl``,
``docs/assets/eval/train_loss.png`` e ``ml/registry.json`` (esquema ``FinetuneMeta``).
"""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from asclepio_ml.config import Config, TrainProfile
from asclepio_ml.plots import plot_train_loss
from asclepio_ml.registry import build_finetune_meta, write_registry
from asclepio_ml.utils import get_device, log, read_jsonl, resolve_dtype, write_json


def _to_prompt_completion(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """messages → {prompt: [system,user], completion: [assistant]} (loss só na resposta)."""
    out: list[dict[str, Any]] = []
    for r in rows:
        msgs = r.get("messages") or []
        if len(msgs) < 2 or msgs[-1].get("role") != "assistant":
            continue
        out.append({"prompt": msgs[:-1], "completion": [msgs[-1]]})
    return out


def _build_dataset(rows: list[dict[str, Any]]):
    from datasets import Dataset

    return Dataset.from_list(_to_prompt_completion(rows))


class JsonlLoggerCallback:
    """Callback do Trainer: grava cada log (loss, lr, eval_loss) em ``train_log.jsonl``."""

    def __init__(self, path: Path) -> None:
        from transformers import TrainerCallback

        self.path = path
        self.rows: list[dict[str, Any]] = []
        parent = self

        class _CB(TrainerCallback):
            @staticmethod
            def _free_cache() -> None:
                """Libera o cache do acelerador. Em MPS o alocador guarda blocos de todos os tamanhos de
                batch já vistos (sequências de tamanhos variados) e o processo pode passar de 40 GB e
                cair em swap; esvaziar o cache a cada N passos mantém o uso estável (~8-12 GB)."""
                import gc

                import torch

                gc.collect()
                if torch.backends.mps.is_available():
                    torch.mps.empty_cache()
                elif torch.cuda.is_available():
                    torch.cuda.empty_cache()

            def on_evaluate(self, args, state, control, **kwargs):
                self._free_cache()

            def on_step_end(self, args, state, control, **kwargs):
                if state.global_step % 5 == 0:
                    self._free_cache()

            def on_log(self, args, state, control, logs=None, **kwargs):
                if not logs:
                    return
                row = {
                    "step": state.global_step,
                    "epoch": round(float(state.epoch or 0), 3),
                    "time": datetime.now().isoformat(timespec="seconds"),
                }
                for k in (
                    "loss",
                    "eval_loss",
                    "learning_rate",
                    "grad_norm",
                    "mean_token_accuracy",
                    "eval_mean_token_accuracy",
                ):
                    if k in logs:
                        row[k] = float(logs[k])
                parent.rows.append(row)
                with parent.path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
                if "loss" in row:
                    log(
                        f"passo {row['step']} · loss {row['loss']:.4f}"
                        + (f" · eval_loss {row['eval_loss']:.4f}" if "eval_loss" in row else "")
                    )

        self.callback = _CB()


def run_train(
    cfg: Config,
    profile: TrainProfile,
    base_model: str | None = None,
    output_dir: Path | None = None,
    device: str | None = None,
    max_train_examples: int | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    import torch
    from peft import LoraConfig
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from trl import SFTConfig, SFTTrainer

    base_model = base_model or cfg.base_model
    device = get_device(device)
    dtype = resolve_dtype(device, profile.dtype)
    run_id = run_id or f"{datetime.now():%Y%m%d-%H%M%S}-{profile.name}"
    run_dir = (output_dir or cfg.paths.runs) / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    log(
        f"run_id={run_id} · base={base_model} · device={device} · dtype={dtype} · perfil={profile.name}"
    )

    # --- dados ---------------------------------------------------------------
    train_rows = read_jsonl(cfg.paths.processed / "train.jsonl")
    val_rows = read_jsonl(cfg.paths.processed / "val.jsonl")
    if not train_rows:
        raise FileNotFoundError(
            f"Sem dados de treino em {cfg.paths.processed}/train.jsonl — rode 'prepare' antes."
        )
    if max_train_examples:
        train_rows = train_rows[:max_train_examples]
        val_rows = val_rows[: max(8, max_train_examples // 10)]
    train_ds, val_ds = _build_dataset(train_rows), (_build_dataset(val_rows) if val_rows else None)
    # Avaliação periódica em um subconjunto fixo do val (curva de loss barata); a avaliação FINAL
    # usa o val completo. Evita que cada eval custe tanto quanto dezenas de passos de treino.
    val_curve_ds = (
        val_ds.select(range(min(len(val_ds), profile.eval_subset))) if val_ds is not None else None
    )
    log(
        f"train={len(train_ds)} · val={len(val_ds) if val_ds else 0} (curva: {len(val_curve_ds) if val_curve_ds else 0}) exemplos (formato prompt/completion)"
    )

    # --- modelo + tokenizer -----------------------------------------------------
    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    model = AutoModelForCausalLM.from_pretrained(base_model, dtype=dtype)
    model.config.use_cache = False  # incompatível com gradient checkpointing; irrelevante no treino
    n_params = sum(p.numel() for p in model.parameters())

    lora_cfg = LoraConfig(
        r=int(cfg.lora.get("r", 16)),
        lora_alpha=int(cfg.lora.get("alpha", 32)),
        lora_dropout=float(cfg.lora.get("dropout", 0.05)),
        target_modules=list(
            cfg.lora.get(
                "target_modules",
                ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
            )
        ),
        bias="none",
        task_type="CAUSAL_LM",
    )

    # --- argumentos de treino --------------------------------------------------------
    use_bf16 = device == "cuda" and dtype == torch.bfloat16
    args = SFTConfig(
        output_dir=str(run_dir / "checkpoints"),
        max_length=profile.max_seq_len,
        per_device_train_batch_size=profile.batch_size,
        per_device_eval_batch_size=profile.batch_size,
        gradient_accumulation_steps=profile.grad_accum,
        num_train_epochs=profile.epochs,
        max_steps=profile.max_steps,
        learning_rate=profile.learning_rate,
        lr_scheduler_type=profile.lr_scheduler,
        warmup_steps=float(
            profile.warmup_ratio
        ),  # float em [0,1) = fração dos passos (transformers ≥ 5)
        weight_decay=profile.weight_decay,
        logging_steps=profile.logging_steps,
        logging_first_step=True,
        eval_strategy="steps" if val_ds is not None else "no",
        prediction_loss_only=True,  # só a loss: NUNCA acumular logits (vocab 152k × seq 1024 explode a memória)
        eval_accumulation_steps=1,
        eval_steps=profile.eval_steps if val_ds is not None else None,
        save_strategy="steps" if profile.save_steps > 0 else "no",
        save_steps=profile.save_steps if profile.save_steps > 0 else 500,
        save_total_limit=1,
        bf16=use_bf16,
        fp16=False,
        gradient_checkpointing=profile.gradient_checkpointing,
        gradient_checkpointing_kwargs={"use_reentrant": False}
        if profile.gradient_checkpointing
        else None,
        report_to="none",
        seed=cfg.seed,
        data_seed=cfg.seed,
        dataloader_pin_memory=device == "cuda",
        completion_only_loss=True,  # loss apenas nos tokens da resposta do assistente
        remove_unused_columns=True,
        disable_tqdm=True,  # já logamos via callback (train_log.jsonl)
    )

    # Agrupar exemplos de tamanho parecido no mesmo batch reduz padding (e tempo) sem mudar a
    # matemática do treino — transformers ≥ 5 expõe isso como `train_sampling_strategy`.
    try:
        args.train_sampling_strategy = "group_by_length"
    except Exception:
        pass

    logger = JsonlLoggerCallback(run_dir / "train_log.jsonl")
    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=train_ds,
        eval_dataset=val_curve_ds,
        processing_class=tokenizer,
        peft_config=lora_cfg,
        callbacks=[logger.callback],
    )
    trainable = sum(p.numel() for p in trainer.model.parameters() if p.requires_grad)
    log(
        f"parâmetros: total {n_params / 1e6:.1f} M · treináveis (LoRA) {trainable / 1e6:.2f} M ({100 * trainable / n_params:.2f}%)"
    )

    # sanity-check didático: quantos tokens recebem loss no 1º exemplo?
    try:
        first = trainer.train_dataset[0]
        mask = first.get("completion_mask") or first.get("assistant_masks")
        if mask is not None:
            log(f"exemplo 0: {len(first['input_ids'])} tokens, {sum(mask)} com loss (assistente)")
    except Exception:
        pass

    # --- treino ---------------------------------------------------------------------------
    t0 = time.time()
    train_out = trainer.train()
    duration_min = (time.time() - t0) / 60
    log(f"treino concluído em {duration_min:.1f} min · loss médio {train_out.training_loss:.4f}")

    final_eval_loss = None
    if val_ds is not None:
        ev = trainer.evaluate(eval_dataset=val_ds)  # val completo
        final_eval_loss = ev.get("eval_loss")
        log(f"eval_loss final: {final_eval_loss:.4f}")

    # --- artefatos -------------------------------------------------------------------------
    adapter_dir = run_dir / "adapter"
    trainer.model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))
    trainer.state.save_to_json(str(run_dir / "trainer_state.json"))
    losses = [h["loss"] for h in trainer.state.log_history if "loss" in h]
    final_train_loss = losses[-1] if losses else train_out.training_loss
    cfg.paths.assets.mkdir(parents=True, exist_ok=True)
    plot_train_loss(logger.rows, cfg.paths.assets / "train_loss.png")
    plot_train_loss(logger.rows, run_dir / "train_loss.png")

    meta = build_finetune_meta(
        run_id=run_id,
        base_model=base_model,
        epochs=round(float(trainer.state.epoch or profile.epochs), 3),
        train_examples=len(train_ds),
        eval_examples=len(val_ds) if val_ds else 0,
        final_train_loss=final_train_loss,
        final_eval_loss=final_eval_loss,
        lora_r=lora_cfg.r,
        lora_alpha=lora_cfg.lora_alpha,
        learning_rate=profile.learning_rate,
        duration_min=duration_min,
        device=device,
        ollama_model=str(cfg.export.get("ollama_model", "asclepio-med")),
        # extras (permitidos pelo contrato)
        profile=profile.name,
        max_seq_len=profile.max_seq_len,
        global_steps=int(trainer.state.global_step),
        effective_batch_size=profile.batch_size * profile.grad_accum,
        dtype=str(dtype).replace("torch.", ""),
        trainable_params=int(trainable),
        total_params=int(n_params),
        lora_dropout=lora_cfg.lora_dropout,
        lora_target_modules=list(lora_cfg.target_modules)
        if not isinstance(lora_cfg.target_modules, str)
        else lora_cfg.target_modules,
        adapter_path=str(adapter_dir.relative_to(cfg.root))
        if adapter_dir.is_relative_to(cfg.root)
        else str(adapter_dir),
        merged_path=None,
        train_loss_plot=str((cfg.paths.assets / "train_loss.png").relative_to(cfg.root)),
    )
    write_json(run_dir / "meta.json", meta)
    write_registry(cfg.paths.registry, meta)
    log(f"adapter → {adapter_dir} · registry → {cfg.paths.registry}")

    # libera memória (útil quando 'all' encadeia export/evaluate no mesmo processo)
    del trainer, model
    if device == "mps":
        torch.mps.empty_cache()
    elif device == "cuda":
        torch.cuda.empty_cache()
    return meta
