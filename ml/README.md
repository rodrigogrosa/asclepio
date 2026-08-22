# `ml/` — Pipeline de fine-tuning e avaliação do Asclépio

> Tech Challenge FIAP · Pós IA para Devs · Fase 3 — requisito: *fine-tuning de um LLM com
> protocolos médicos do hospital, FAQs de médicos e modelos de laudos/receitas/procedimentos;
> preparação dos dados com preprocessing, anonimização e curadoria; relatório com explicação do
> fine-tuning e avaliação do modelo.*

Este pacote (`asclepio_ml`) transforma a base de conhecimento fictícia do HU-FIAP em um modelo
**`asclepio-med`** (LoRA sobre `Qwen/Qwen2.5-0.5B-Instruct`, servido pelo Ollama) e mede, com
números, o que o fine-tuning mudou. O relatório técnico completo está em
[`docs/FINE_TUNING.md`](../docs/FINE_TUNING.md); os números mais recentes em
[`ml/reports/eval_latest.md`](reports/eval_latest.md).

---

## 1. Visão geral do pipeline

```
 data/knowledge_base/            data/synthetic/
 ├─ protocolos/PROT-001..016     ├─ instructions_seed.jsonl (233 instruções)
 ├─ modelos_documentos/MOD-001..010   └─ (pacientes sintéticos gerados em memória)
 └─ faq/perguntas_frequentes.jsonl (167 FAQs)
            │
            ▼  prepare  (carregar → gerar → augmentar → ANONIMIZAR → curar → dividir)
 data/processed/{train,val,test}.jsonl + dataset_stats.json + DATASET_CARD.md
            │
            ▼  train    (LoRA r=16 · TRL SFTTrainer · loss só nos tokens do assistente)
 ml/runs/<run_id>/{adapter, trainer_state.json, train_log.jsonl}  +  ml/registry.json
            │
            ▼  export   (merge_and_unload → safetensors → Modelfile → `ollama create asclepio-med`)
 ml/models/asclepio-med/{model.safetensors, tokenizer*, Modelfile, export_report.json}
            │
            ▼  evaluate (base × fine-tuned × asclepio-med(ollama) × llama3.1:8b · RAG hit@5/MRR · LLM-juiz)
 ml/reports/eval_latest.{json,md}  +  docs/assets/eval/*.png
```

Cada etapa é um subcomando da CLI e um módulo com docstring explicando *o porquê* das decisões:

| etapa | módulo | saída |
|---|---|---|
| `prepare` | `asclepio_ml/data_prep.py` | dataset *messages* anonimizado e curado |
| `train` | `asclepio_ml/train.py` | adapter LoRA + registry (`FinetuneMeta`) + `train_loss.png` |
| `export` | `asclepio_ml/export.py` | modelo fundido + `Modelfile` + modelo `asclepio-med` no Ollama |
| `evaluate` | `asclepio_ml/evaluate.py`, `metrics.py`, `rag_eval.py`, `plots.py` | `eval_latest.json` (`EvalReport`) + MD + PNGs |
| prompts | `asclepio_ml/prompts.py` | system prompt do Asclépio, templates de paráfrase, rubrica do juiz, conjunto de segurança |
| config | `ml/configs/finetune.yaml` | perfis `quick` / `full`, LoRA, caminhos, avaliação |

O núcleo compartilhado (`packages/asclepio_core`) fornece o **anonimizador**, os **guardrails**,
as **regras clínicas** (`assess_risk`), a leitura/chunking da **base de conhecimento** e os
**pacientes sintéticos** — o mesmo código usado pelo backend, garantindo consistência ML ⇄ produto.

## 2. Como rodar

Sempre a partir da **raiz do monorepo** (o `uv` resolve o workspace e a venv `.venv`):

```bash
uv sync --all-packages                       # instala tudo (torch, transformers, peft, trl, ...)

uv run python -m asclepio_ml --help
uv run python -m asclepio_ml prepare                         # → data/processed/
uv run python -m asclepio_ml train --profile quick           # smoke test (~2-3 min) — valida o pipeline
uv run python -m asclepio_ml train --profile full            # execução real (~25-40 min em M-series)
uv run python -m asclepio_ml export                          # merge + Modelfile + `ollama create asclepio-med`
uv run python -m asclepio_ml evaluate --include-reference    # base × fine-tuned × asclepio-med × llama3.1:8b
uv run python -m asclepio_ml all --profile full --include-reference   # tudo em sequência
uv run python -m asclepio_ml synthetic-patients              # → data/synthetic/patients.json
```

Flags úteis:

| flag | onde | efeito |
|---|---|---|
| `--profile quick\|full` | `train`, `all` | perfil de treino (ver §4) |
| `--base-model <hf-id>` | `train`, `export`, `evaluate`, `all` | troca o modelo base (ver §5) |
| `--output <dir>` | todos | redireciona a saída da etapa |
| `--with-public` | `prepare` | mistura ≤ 10 % de PubMedQA/MedQuAD (requer rede). **Usado na execução oficial** (`make prepare`); `make prepare-offline` roda sem eles |
| `--max-samples N` | `evaluate` | amostra do `test.jsonl` (padrão 120) |
| `--include-reference` | `evaluate` | adiciona `llama3.1:8b` (Ollama) como referência |
| `--no-judge` / `--tfidf` | `evaluate` | desliga o LLM-juiz / força TF-IDF no RAG (sem Ollama) |
| `--no-ollama` | `export`, `all` | só funde e gera `Modelfile`, sem chamar o Ollama |
| `--gguf` | `export` | força conversão GGUF (llama.cpp) em vez de importar safetensors |
| `-c <yaml>` | todos | outro arquivo de configuração (os testes usam um YAML temporário) |

Testes (sem rede, sem treino, ~5 s):

```bash
uv run pytest ml/tests -q
```

## 3. O que cada etapa faz (resumo didático)

### `prepare` — dados
1. **Carregar**: seed de instruções (7 categorias: `protocolo`, `documento`, `paciente_contexto`,
   `recusa_prescricao`, `fora_escopo`, `identidade_limites`, `anonimizacao_seguranca`), FAQ,
   seções H2 dos 16 protocolos e dos 10 modelos de documentos.
2. **Gerar exemplos programáticos**: "O que diz o PROT-00X sobre *seção*?" → resumo da seção com
   `Fonte: PROT-00X › seção`; pares P/R das "Perguntas frequentes da equipe"; uma pergunta de dose
   por linha da tabela de fármacos (em linguagem sugestiva); "Me dê a estrutura do MOD-00X";
   e **contexto de paciente** a partir de `generate_patients()` + `assess_risk()` (contexto já
   anonimizado, resposta templada com achados/critérios/sugestões/fontes).
3. **Augmentar**: 3–5 paráfrases templadas por pergunta (mesma resposta, mesmo `group`).
4. **Anonimizar**: *todo* texto passa pelo `Anonymizer` (CPF, CNS, RG, telefone, e-mail, CEP,
   data de nascimento, endereço, nomes com contexto) — contagem por tipo vai para o dataset card.
5. **Curar**: remove vazios/curtos, dedupe exato e aproximado, trunca respostas longas em
   parágrafo, **cap por categoria**, garante aviso de validação humana (`guardrails.DISCLAIMER`)
   nas categorias clínicas e que recusas são recusas (`is_refusal`).
6. **Dividir** 85 / 7,5 / 7,5 estratificado por categoria, **agrupado** (paráfrases da mesma
   pergunta nunca se separam entre train/test → sem vazamento).
7. **System prompt** único (`prompts.SYSTEM_PROMPT`) em todos os exemplos, no `Modelfile` e na avaliação.

### `train` — LoRA
- Base `Qwen/Qwen2.5-0.5B-Instruct` (ungated, 494 M parâmetros, roda em MPS/CPU).
- LoRA `r=16, alpha=32, dropout=0.05` em `q/k/v/o/gate/up/down` → **8,8 M parâmetros treináveis (1,78 %)**.
- TRL `SFTTrainer` com dataset *prompt/completion* → `completion_only_loss` (loss só nos tokens do
  assistente). Device automático (cuda → mps → cpu); dtype bf16 em CUDA, **fp32 em MPS/CPU**
  (estabilidade; testamos bf16 em MPS: ~15 % mais rápido, mas mantivemos fp32 por segurança numérica).
- `train_sampling_strategy=group_by_length` (menos padding), LR 2e-4 cosine, warmup 5 %, batch
  efetivo 16, `max_seq_len` 1024, eval no `val` a cada 50 passos.
- Artefatos: `ml/runs/<run_id>/adapter`, `trainer_state.json`, `train_log.jsonl`,
  `docs/assets/eval/train_loss.png` e `ml/registry.json` (esquema `FinetuneMeta` do contrato).

### `export` — Ollama
- `PeftModel.merge_and_unload()` → `ml/models/asclepio-med/` (safetensors fp16 + tokenizer).
- Grava chaves legadas no `config.json` (`rope_theta`, `torch_dtype`): transformers ≥ 5 move o
  `rope_theta` para `rope_parameters`, e sem isso o conversor do Ollama importa o Qwen2 com RoPE
  errado (texto degenerado — bug encontrado e corrigido nesta entrega).
- `Modelfile` com `FROM ./`, `TEMPLATE` ChatML (Qwen), `SYSTEM` = prompt do Asclépio,
  `PARAMETER temperature 0.1`, stops. `ollama create asclepio-med -f Modelfile`.
- Fallback automático: se a importação de safetensors falhar, converte para GGUF com
  `convert_hf_to_gguf.py` (llama.cpp clonado em `ml/.cache/llama.cpp`) e usa `FROM ./asclepio-med.gguf`.
- Verificação: pergunta "Qual o alvo de lactato na sepse segundo o protocolo?" via API do Ollama
  (resposta salva em `export_report.json`).

### `evaluate` — métricas
| métrica | o que mede |
|---|---|
| `rouge_l`, `bleu` | sobreposição lexical com a resposta de referência |
| `keyword_coverage` | fração de números/doses, fármacos e IDs `PROT-`/`MOD-` da referência presentes na resposta |
| `citation_rate` | cita o mesmo `PROT-`/`MOD-` que a referência cita |
| `guardrail_compliance` | sem `linguagem_prescritiva`/`pii_na_saida` (`guardrails.check_output`) e recusa correta no conjunto de segurança |
| `safety_refusal_rate` | (extra) % de recusas corretas só nos prompts adversariais (`prompts.SAFETY_PROMPTS`) |
| `judge_score` | LLM-juiz `llama3.1:8b` (fidelidade/segurança/clareza, 1–5) — pulado com aviso se o Ollama não responder |
| `avg_latency_ms`, `n` | latência média por resposta e nº de itens |
| RAG `hit_rate_at_5`, `mrr` | perguntas do FAQ → chunk do protocolo correto (embeddings `nomic-embed-text`; fallback TF-IDF) |

Saídas: `ml/reports/eval_latest.json` (esquema `EvalReport`), `ml/reports/eval_latest.md` e
`docs/assets/eval/{metrics_comparison,bleu,latency,safety,rag,train_loss}.png`.

## 4. Perfis e tempos esperados (MacBook M-series, 48 GB, MPS)

| perfil | uso | max_seq | passos | tempo medido |
|---|---|---|---|---|
| `quick` | smoke test do pipeline | 512 | 50 (ou `--max-train-examples 80` → 20) | ~1 min de treino + ~1 min de carga |
| `full` | execução real | 1024 | 2 épocas = 216 passos (batch efetivo 16 = 2 × 8 acúmulos) | **21,5 min medidos** (≈ 6 s/passo, fp32, ~10–15 GB de RAM) |

Outros tempos medidos (run `20260821-214718-full`): `prepare` ≈ 10 s · `export` (merge + `ollama create` + verificação) ≈ 1,5 min ·
`evaluate` com 120 amostras + 15 de segurança: 2,9 min (base, HF/MPS), 2,8 min (fine-tuned, HF/MPS), 1,9 min (`asclepio-med` via Ollama),
6,1 min (`llama3.1:8b`), ~4 min de LLM-juiz (60 itens × 4 modelos), ~1 min de RAG → **≈ 15 min no total**.

Em CUDA (bf16) os tempos de treino caem ~5-10×; em CPU sobem ~5-8× (use `quick`).

## 5. Trocar o modelo base

```bash
# Llama 3.2 1B (gated — aceite a licença no HF e exporte HF_TOKEN)
export HF_TOKEN=hf_xxx
uv run python -m asclepio_ml train --profile full --base-model meta-llama/Llama-3.2-1B-Instruct
uv run python -m asclepio_ml export  --base-model meta-llama/Llama-3.2-1B-Instruct
# TinyLlama 1.1B (ungated, template Zephyr)
uv run python -m asclepio_ml train --profile full --base-model TinyLlama/TinyLlama-1.1B-Chat-v1.0
# Qwen2.5 1.5B (mais qualidade, ~3x mais lento)
uv run python -m asclepio_ml train --profile full --base-model Qwen/Qwen2.5-1.5B-Instruct
```

O `export` detecta a família (`detect_family`) e escolhe o template do `Modelfile` (ChatML, Llama 3,
Zephyr). Os módulos-alvo do LoRA (`q/k/v/o/gate/up/down_proj`) valem para Qwen2, Llama e TinyLlama.
Para outras arquiteturas ajuste `lora.target_modules` no YAML. Você também pode fixar o modelo por
variável de ambiente: `ASCLEPIO_BASE_MODEL=...`.

## 6. Troubleshooting

| sintoma | causa provável | o que fazer |
|---|---|---|
| treino muito lento em MPS (> 20 s/passo) | batch grande em fp32 → pressão de memória unificada | use `batch_size: 4`, `grad_accum: 4` (padrão); reduza `max_seq_len` |
| `NaN` na loss em MPS | fp16/bf16 instável | `dtype: auto` (fp32 em MPS) — já é o padrão |
| operação sem kernel MPS | torch antigo | a CLI define `PYTORCH_ENABLE_MPS_FALLBACK=1` automaticamente |
| `ollama create` falha ao importar safetensors | arquitetura não suportada pelo conversor | o `export` tenta GGUF automaticamente (`--gguf` força) |
| `asclepio-med` responde texto degenerado | `config.json` sem `rope_theta` (transformers ≥ 5) | já corrigido em `export._write_legacy_config_keys`; rode `export` de novo |
| `judge_score: null` / RAG `tfidf` | Ollama fora do ar ou sem `llama3.1:8b`/`nomic-embed-text` | `ollama serve`, `ollama pull llama3.1:8b nomic-embed-text` |
| modelo gated (401) | Llama 3.x exige aceite de licença | `export HF_TOKEN=...` |
| `test.jsonl não encontrado` | `prepare` não rodou | `uv run python -m asclepio_ml prepare` |
| memória insuficiente em CUDA | modelo maior / batch grande | `gradient_checkpointing: true`, `batch_size: 2`, `grad_accum: 8` |

## 8. Resultados da última execução (resumo)

Run `20260821-214718-full` · Qwen2.5-0.5B-Instruct · LoRA r=16 · 2 épocas (216 passos) · 21,5 min em MPS · loss treino 0,75 · loss val 1,31.

| modelo | ROUGE-L | BLEU | cobertura kw | citação | guardrails | recusa segura | juiz (1-5) | latência |
|---|---|---|---|---|---|---|---|---|
| base (Qwen2.5-0.5B-Instruct) | 0,131 | 3,2 | 0,175 | 0,169 | 0,741 | 0,467 | 3,58 | 1 250 ms |
| **fine-tuned (transformers)** | **0,366** | **28,0** | **0,267** | 0,225 | 0,889 | 0,600 | 3,67 | 1 230 ms |
| **asclepio-med (Ollama)** | **0,366** | **28,9** | **0,277** | **0,247** | **0,926** | **0,800** | 3,67 | **853 ms** |
| llama3.1:8b (referência) | 0,133 | 3,5 | 0,108 | 0,157 | 0,815 | 0,533 | **4,37** | 2 708 ms |

RAG (FAQ → protocolo): hit@5 **0,970**, MRR **0,910** (nomic-embed-text; TF-IDF 0,976 / 0,898), 167 consultas, 287 chunks.
Análise completa em [`docs/FINE_TUNING.md`](../docs/FINE_TUNING.md).

## 9. Estrutura de arquivos

```
ml/
├── asclepio_ml/        pacote (cli, config, prompts, data_prep, train, export, evaluate, metrics, rag_eval, plots, registry, utils)
├── configs/finetune.yaml
├── tests/              pytest (fixtures com mini base de conhecimento em tests/fixtures)
├── reports/            eval_latest.json / eval_latest.md (gerados)
├── registry.json       FinetuneMeta do último run (gerado)
├── runs/               adapters e logs por run (gitignored)
├── models/asclepio-med/ modelo fundido + Modelfile (gitignored)
└── .cache/             llama.cpp, artefatos de smoke (gitignored)
```
