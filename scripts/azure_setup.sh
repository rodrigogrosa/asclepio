#!/usr/bin/env bash
# =====================================================================
#  azure_setup.sh — cria os recursos Azure da Fase 4 (Speech + Language, tier F0 gratuito)
#  e grava as chaves no .env. Requer a Azure CLI (`az`) e uma assinatura (ex.: Azure for Students).
#  Uso: ./scripts/azure_setup.sh [grupo] [região]      (padrão: rg-asclepio brazilsouth)
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."
RG="${1:-rg-asclepio}"
LOC="${2:-brazilsouth}"
SUFFIX="$(LC_ALL=C tr -dc 'a-z0-9' </dev/urandom | head -c 5 || true)"
SPEECH="asclepio-speech-${SUFFIX}"
LANG_RES="asclepio-language-${SUFFIX}"

command -v az >/dev/null || { echo "Azure CLI não encontrada. Instale: https://learn.microsoft.com/cli/azure/install-azure-cli (macOS: brew install azure-cli)"; exit 1; }
az account show >/dev/null 2>&1 || az login >/dev/null
echo "▶ Assinatura: $(az account show --query name -o tsv)"
az group create -n "$RG" -l "$LOC" -o none
echo "▶ Criando Speech (F0) $SPEECH em $LOC"
az cognitiveservices account create -n "$SPEECH" -g "$RG" -l "$LOC" --kind SpeechServices --sku F0 --yes -o none
echo "▶ Criando Language (F0) $LANG_RES em $LOC — inclui Text Analytics for Health e sentimento"
az cognitiveservices account create -n "$LANG_RES" -g "$RG" -l "$LOC" --kind TextAnalytics --sku F0 --yes -o none

SPEECH_KEY=$(az cognitiveservices account keys list -n "$SPEECH" -g "$RG" --query key1 -o tsv)
LANG_KEY=$(az cognitiveservices account keys list -n "$LANG_RES" -g "$RG" --query key1 -o tsv)
LANG_ENDPOINT=$(az cognitiveservices account show -n "$LANG_RES" -g "$RG" --query properties.endpoint -o tsv)

[[ -f .env ]] || cp .env.example .env
setvar() { if grep -qE "^$1=" .env; then sed -i.bak "s|^$1=.*|$1=$2|" .env && rm -f .env.bak; else echo "$1=$2" >> .env; fi; }
setvar AZURE_SPEECH_KEY "$SPEECH_KEY"
setvar AZURE_SPEECH_REGION "$LOC"
setvar AZURE_LANGUAGE_KEY "$LANG_KEY"
setvar AZURE_LANGUAGE_ENDPOINT "$LANG_ENDPOINT"
echo "✔ Chaves gravadas no .env (não versionado). Confira com: make azure-check · aplique com: make up"
echo "  Para remover tudo depois: az group delete -n $RG --yes"
