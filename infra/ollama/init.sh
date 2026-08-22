#!/bin/sh
# Inicialização automática do Ollama (roda como job one-shot no docker compose):
#  1) espera o servidor responder; 2) baixa os modelos necessários; 3) cria o modelo fine-tunado
#  `asclepio-med` a partir de ml/models/asclepio-med/Modelfile (se o pipeline de ML já foi executado).
set -eu
OLLAMA_HOST="${OLLAMA_HOST:-http://ollama:11434}"
export OLLAMA_HOST
MODELS="${OLLAMA_PULL_MODELS:-nomic-embed-text llama3.1:8b}"
echo "[ollama-init] aguardando $OLLAMA_HOST ..."
i=0
until ollama list >/dev/null 2>&1; do
  i=$((i+1)); [ "$i" -gt 120 ] && echo "[ollama-init] timeout" && exit 1
  sleep 2
done
for m in $MODELS; do
  if ollama list | awk '{print $1}' | grep -qx "$m" || ollama list | awk '{print $1}' | grep -q "^$m:"; then
    echo "[ollama-init] modelo já presente: $m"
  else
    echo "[ollama-init] baixando $m ..."; ollama pull "$m"
  fi
done
if [ -f /models/asclepio-med/Modelfile ]; then
  if ollama list | awk '{print $1}' | grep -q "^asclepio-med"; then
    echo "[ollama-init] asclepio-med já existe (use 'make ollama-create' para recriar)"
  else
    echo "[ollama-init] criando modelo fine-tunado asclepio-med ..."
    cd /models/asclepio-med && ollama create asclepio-med -f Modelfile && echo "[ollama-init] asclepio-med criado"
  fi
else
  echo "[ollama-init] ml/models/asclepio-med/Modelfile não encontrado — a API usará o modelo fallback até você rodar 'make finetune export'."
fi
echo "[ollama-init] pronto:"; ollama list
