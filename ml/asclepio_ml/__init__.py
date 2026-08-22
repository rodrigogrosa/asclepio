"""asclepio_ml — pipeline de ML do Asclépio (Tech Challenge FIAP · Fase 3).

Etapas (cada uma é um subcomando da CLI ``python -m asclepio_ml``):

1. ``prepare``  → monta o dataset de instrução (seed + FAQ + protocolos + modelos +
   pacientes sintéticos), **anonimiza**, cura, balanceia e divide em train/val/test.
2. ``train``    → fine-tuning com **LoRA** (PEFT + TRL SFTTrainer) sobre um modelo base
   pequeno que roda em Apple Silicon (MPS), CUDA ou CPU.
3. ``export``   → funde o adapter no modelo base e registra o modelo ``asclepio-med`` no Ollama.
4. ``evaluate`` → compara base × fine-tuned (× referência) com métricas automáticas,
   guardrails, LLM-juiz e métricas de RAG; gera relatório JSON/MD e gráficos.

O pacote é deliberadamente didático: cada módulo explica *por que* faz o que faz.
"""

__version__ = "1.0.0"
