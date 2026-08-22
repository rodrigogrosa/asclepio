#!/usr/bin/env bash
# =====================================================================
#  bootstrap.sh — instalação 100% automatizada do Asclépio via Docker
#  Uso: ./scripts/bootstrap.sh [--profile observability] [--no-wait-models]
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

PINK='\033[1;35m'; GRN='\033[1;32m'; YEL='\033[1;33m'; RED='\033[1;31m'; NC='\033[0m'
say()  { echo -e "${PINK}▶${NC} $*"; }
ok()   { echo -e "${GRN}✔${NC} $*"; }
warn() { echo -e "${YEL}!${NC} $*"; }
die()  { echo -e "${RED}✖${NC} $*"; exit 1; }

PROFILE_EXTRA=""; WAIT_MODELS=1
for a in "$@"; do
  case "$a" in
    --profile) shift; ;;
    --profile=*) PROFILE_EXTRA="${a#*=}";;
    observability|gateway) PROFILE_EXTRA="$a";;
    --no-wait-models) WAIT_MODELS=0;;
  esac
done
# suporta "--profile observability" (dois args)
if [[ "${1:-}" == "--profile" && -n "${2:-}" ]]; then PROFILE_EXTRA="$2"; fi

echo -e "${PINK}"
cat <<'BANNER'
   ___   _____ _____ __    __________  ________
  / _ | / ___// ___// /   / ____/ __ \/  _/ __ \
 / __ |(__  )/ /__ / /___/ __/ / /_/ // // / / /
/_/ |_/____/ \___//_____/_____/ ____/___/\____/   Assistente Clínico Inteligente · FIAP
                             /_/
BANNER
echo -e "${NC}"

# ---------- 1) pré-requisitos ----------
say "Verificando pré-requisitos"
command -v docker >/dev/null || die "Docker não encontrado. Instale o Docker Desktop: https://docs.docker.com/get-docker/"
docker info >/dev/null 2>&1 || die "Docker não está em execução. Abra o Docker Desktop e tente novamente."
docker compose version >/dev/null 2>&1 || die "Docker Compose v2 não encontrado."
ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) · $(docker compose version --short)"

# ---------- 2) .env ----------
if [[ ! -f .env ]]; then
  cp .env.example .env
  # gera um SECRET_KEY aleatório
  SECRET=$(python3 -c 'import secrets;print(secrets.token_urlsafe(48))' 2>/dev/null || openssl rand -base64 48 | tr -d '\n')
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=${SECRET}|" .env && rm -f .env.bak
  ok ".env criado a partir de .env.example (SECRET_KEY gerado)"
else
  ok ".env já existe (mantido)"
fi

# ---------- 3) Ollama: host ou container? ----------
PROFILES=()
OLLAMA_URL_FOR_CONTAINERS="http://ollama:11434"
if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
  ok "Ollama detectado no host (localhost:11434) — será usado pelos containers (mais rápido em Mac/Apple Silicon)"
  OLLAMA_URL_FOR_CONTAINERS="http://host.docker.internal:11434"
  if command -v ollama >/dev/null; then
    for m in nomic-embed-text "${LLM_FALLBACK_MODEL:-llama3.1:8b}"; do
      if ollama list | awk '{print $1}' | grep -q "^${m}"; then ok "modelo presente no host: $m"; else say "baixando $m no Ollama do host..."; ollama pull "$m"; fi
    done
    if [[ -f ml/models/asclepio-med/Modelfile ]] && ! ollama list | awk '{print $1}' | grep -q '^asclepio-med'; then
      say "criando modelo fine-tunado asclepio-med no Ollama do host..."; (cd ml/models/asclepio-med && ollama create asclepio-med -f Modelfile) || warn "falha ao criar asclepio-med (a API usará o fallback)"
    fi
  fi
else
  warn "Ollama não encontrado no host → subindo Ollama em container (perfil 'ollama'). Em Macs, instalar o Ollama nativo (https://ollama.com) é bem mais rápido."
  PROFILES+=(--profile ollama)
fi
# grava a URL vista pelos CONTAINERS no .env (OLLAMA_BASE_URL continua sendo a do host, para `make dev`)
if grep -q '^OLLAMA_BASE_URL_DOCKER=' .env; then sed -i.bak "s|^OLLAMA_BASE_URL_DOCKER=.*|OLLAMA_BASE_URL_DOCKER=${OLLAMA_URL_FOR_CONTAINERS}|" .env && rm -f .env.bak; else echo "OLLAMA_BASE_URL_DOCKER=${OLLAMA_URL_FOR_CONTAINERS}" >> .env; fi

if [[ -n "$PROFILE_EXTRA" ]]; then
  PROFILES+=(--profile "$PROFILE_EXTRA")
  if [[ "$PROFILE_EXTRA" == "observability" ]]; then
    if grep -q '^LANGFUSE_ENABLED=' .env; then sed -i.bak "s|^LANGFUSE_ENABLED=.*|LANGFUSE_ENABLED=true|" .env && rm -f .env.bak; else echo "LANGFUSE_ENABLED=true" >> .env; fi
  fi
fi

# ---------- 3b) portas ----------
API_PORT=$(grep -E '^API_PORT=' .env | cut -d= -f2 || true); API_PORT=${API_PORT:-8000}
WEB_PORT=$(grep -E '^WEB_PORT=' .env | cut -d= -f2 || true); WEB_PORT=${WEB_PORT:-3000}
for spec in "API:$API_PORT" "Web:$WEB_PORT"; do
  name=${spec%%:*}; port=${spec##*:}
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
    warn "porta $port ($name) já está em uso no host. Ajuste ${name^^}_PORT no .env (ex.: API_PORT=8001 / WEB_PORT=3001) ou libere a porta."
  fi
done

# CORS: garante que a origem da Web (porta escolhida) esteja liberada na API
CORS_LINE="CORS_ORIGINS=http://localhost:${WEB_PORT},http://127.0.0.1:${WEB_PORT},http://localhost:3000,http://127.0.0.1:3000"
if grep -q '^CORS_ORIGINS=' .env; then sed -i.bak "s|^CORS_ORIGINS=.*|${CORS_LINE}|" .env && rm -f .env.bak; else echo "$CORS_LINE" >> .env; fi

# ---------- 4) build + up ----------
say "Construindo imagens (primeira vez pode levar alguns minutos)"
docker compose ${PROFILES[@]+"${PROFILES[@]}"} build
say "Subindo serviços ${PROFILES[*]:-}"
if ! docker compose ${PROFILES[@]+"${PROFILES[@]}"} up -d; then
  die "falha ao subir os containers. Se o erro for 'port is already allocated', altere API_PORT/WEB_PORT no .env ou reinicie o Docker Desktop e rode 'make up' de novo."
fi

# ---------- 5) aguarda saúde ----------
say "Aguardando API ficar saudável (indexação da base de conhecimento)..."
for i in $(seq 1 90); do
  if curl -fsS "http://localhost:${API_PORT}/health" >/dev/null 2>&1; then ok "API pronta"; break; fi
  sleep 2
  [[ $i -eq 90 ]] && { docker compose logs --tail=50 api; die "API não respondeu a tempo"; }
done
if [[ $WAIT_MODELS -eq 1 && " ${PROFILES[*]:-} " == *"ollama"* ]]; then
  say "Aguardando download dos modelos no Ollama (ollama-init)..."
  docker compose --profile ollama logs -f ollama-init 2>/dev/null | sed -n '/pronto:/q' || true
fi
for i in $(seq 1 60); do
  if curl -fsS "http://localhost:${WEB_PORT}" >/dev/null 2>&1; then ok "Web pronta"; break; fi
  sleep 2
done

# ---------- 6) smoke ----------
HEALTH=$(curl -fsS "http://localhost:${API_PORT}/health")
ok "Health: $HEALTH"
echo ""
echo -e "${GRN}Tudo pronto!${NC}"
echo -e "  🌐 Web:        http://localhost:${WEB_PORT}"
echo -e "  🔌 API (docs): http://localhost:${API_PORT}/docs"
echo -e "  📈 Métricas:   http://localhost:${API_PORT}/metrics"
LITELLM_PORT=$(grep -E '^LITELLM_PORT=' .env | cut -d= -f2 || true); LITELLM_PORT=${LITELLM_PORT:-4000}
LANGFUSE_PORT=$(grep -E '^LANGFUSE_PORT=' .env | cut -d= -f2 || true); LANGFUSE_PORT=${LANGFUSE_PORT:-3001}
[[ "$PROFILE_EXTRA" == "observability" || "$PROFILE_EXTRA" == "gateway" ]] && echo -e "  🔀 LiteLLM UI: http://localhost:${LITELLM_PORT}/ui  (chave: sk-asclepio-dev)"
[[ "$PROFILE_EXTRA" == "observability" ]] && echo -e "  🔭 Langfuse:   http://localhost:${LANGFUSE_PORT}  (admin@asclepio.fiap / Asclepio@2026)"
echo -e "  👤 Login demo: dra.ana@asclepio.fiap / Asclepio@2026  (outros em docs/CONTRATO_API.md)"
echo ""
