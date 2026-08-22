# Avaliação — Asclépio (fine-tuning LoRA)

Gerado em 2026-08-22T00:20:31 · run `20260821-234215-full` · base `Qwen/Qwen2.5-0.5B-Instruct` · device `mps`

## Modelos (conjunto de teste: 120 amostras · segurança: 15 prompts)
| modelo | ROUGE-L | BLEU | cobertura kw | citação | guardrails | recusa segura | juiz (1-5) | latência (ms) | n |
|---|---|---|---|---|---|---|---|---|---|
| **base** | 0.125 | 3.0 | 0.167 | 0.223 | 0.770 | 0.467 | 3.62 | 1,327 | 135 |
| **fine-tuned** | 0.355 | 26.8 | 0.239 | 0.319 | 0.956 | 0.867 | 3.68 | 1,320 | 135 |
| **asclepio-med (ollama)** | 0.364 | 27.6 | 0.241 | 0.340 | 0.948 | 0.800 | 3.73 | 899 | 135 |
| **llama3.1:8b (referência)** | 0.124 | 3.8 | 0.117 | 0.202 | 0.844 | 0.533 | 4.30 | 2,701 | 135 |

> `guardrails` = % de respostas sem linguagem prescritiva imperativa e sem PII (+ recusa correta no conjunto de segurança).
> `recusa segura` = % de recusas corretas apenas no conjunto de segurança. `juiz` = LLM-juiz `llama3.1:8b` (amostra de 60 itens).

## RAG (perguntas do FAQ → protocolo correto)
| método | hit@5 | MRR | consultas | chunks |
|---|---|---|---|---|
| ollama:nomic-embed-text | 0.970 | 0.910 | 167 | 287 |
| TF-IDF (baseline) | 0.976 | 0.898 | 167 | 287 |

## Análise curta
- ROUGE-L: +0.230 · cobertura de palavras-chave: +0.073 · taxa de citação: +0.096 (fine-tuned − base).
- Guardrails: +0.185 · recusa segura: +0.400 · juiz: +0.067.
- Leitura: o fine-tuning ensina *formato institucional* (citar PROT-/MOD-, aviso de validação, recusar prescrição) — é isso que as métricas de citação/guardrails capturam; ROUGE/BLEU medem sobreposição lexical com a resposta de referência e sobem quando o modelo reproduz a terminologia dos protocolos.
- Limitações: referências únicas (uma resposta 'correta' por pergunta), modelo base de 0,5 B parâmetros, avaliação automática + LLM-juiz (não substitui validação clínica humana).

## Gráficos
![métricas](../../docs/assets/eval/metrics_comparison.png)
![latência](../../docs/assets/eval/latency.png)
![segurança](../../docs/assets/eval/safety.png)
![rag](../../docs/assets/eval/rag.png)
![loss](../../docs/assets/eval/train_loss.png)
