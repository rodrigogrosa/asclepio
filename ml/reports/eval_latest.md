# Avaliação — Asclépio (fine-tuning LoRA)

Gerado em 2026-08-21T22:24:54 · run `20260821-214718-full` · base `Qwen/Qwen2.5-0.5B-Instruct` · device `mps`

## Modelos (conjunto de teste: 120 amostras · segurança: 15 prompts)
| modelo | ROUGE-L | BLEU | cobertura kw | citação | guardrails | recusa segura | juiz (1-5) | latência (ms) | n |
|---|---|---|---|---|---|---|---|---|---|
| **base** | 0.131 | 3.2 | 0.175 | 0.169 | 0.741 | 0.467 | 3.58 | 1,250 | 135 |
| **fine-tuned** | 0.366 | 28.0 | 0.267 | 0.225 | 0.889 | 0.600 | 3.67 | 1,230 | 135 |
| **asclepio-med (ollama)** | 0.366 | 28.9 | 0.277 | 0.247 | 0.926 | 0.800 | 3.67 | 853 | 135 |
| **llama3.1:8b (referência)** | 0.133 | 3.5 | 0.108 | 0.157 | 0.815 | 0.533 | 4.37 | 2,708 | 135 |

> `guardrails` = % de respostas sem linguagem prescritiva imperativa e sem PII (+ recusa correta no conjunto de segurança).
> `recusa segura` = % de recusas corretas apenas no conjunto de segurança. `juiz` = LLM-juiz `llama3.1:8b` (amostra de 60 itens).

## RAG (perguntas do FAQ → protocolo correto)
| método | hit@5 | MRR | consultas | chunks |
|---|---|---|---|---|
| ollama:nomic-embed-text | 0.970 | 0.910 | 167 | 287 |
| TF-IDF (baseline) | 0.976 | 0.898 | 167 | 287 |

## Análise curta
- ROUGE-L: +0.235 · cobertura de palavras-chave: +0.092 · taxa de citação: +0.056 (fine-tuned − base).
- Guardrails: +0.148 · recusa segura: +0.133 · juiz: +0.083.
- Leitura: o fine-tuning ensina *formato institucional* (citar PROT-/MOD-, aviso de validação, recusar prescrição) — é isso que as métricas de citação/guardrails capturam; ROUGE/BLEU medem sobreposição lexical com a resposta de referência e sobem quando o modelo reproduz a terminologia dos protocolos.
- Limitações: referências únicas (uma resposta 'correta' por pergunta), modelo base de 0,5 B parâmetros, avaliação automática + LLM-juiz (não substitui validação clínica humana).

## Gráficos
![métricas](../../docs/assets/eval/metrics_comparison.png)
![latência](../../docs/assets/eval/latency.png)
![segurança](../../docs/assets/eval/safety.png)
![rag](../../docs/assets/eval/rag.png)
![loss](../../docs/assets/eval/train_loss.png)
