# ADR-0003: Fine-tuning com LoRA em modelo pequeno e serving via Ollama

- **Status**: aceito · **Data**: 2026-08-21

## Contexto
Precisamos treinar de verdade (não só descrever) em hardware de aluno (Mac Apple Silicon/CPU), exportar e integrar ao LangChain.

## Decisão
**LoRA (PEFT)** sobre `Qwen/Qwen2.5-0.5B-Instruct` (ungated, roda em MPS em minutos), com opção de `Llama-3.2-1B/3B-Instruct` (gated). Merge do adapter → `Modelfile` → **`ollama create asclepio-med`**. A API usa `ChatOllama` e faz fallback para `llama3.1:8b` se o modelo não existir.

## Alternativas
- Full fine-tuning — inviável no hardware. - QLoRA 4-bit — bitsandbytes não funciona em MPS. - Servir com vLLM/TGI — pesado para demo local.

## Consequências
+ Pipeline reprodutível e barato; modelo local sem custos. − Modelo pequeno é limitado em raciocínio; por isso o produto combina **fine-tuning + RAG + guardrails** (o fine-tuning ajusta tom/formato/escopo e conhecimento institucional; o RAG garante fatos atualizados e citáveis).
