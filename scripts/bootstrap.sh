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

# ---------- 2b) senhas dos usuários reais (geradas uma vez, guardadas no .env) ----------
gen_pwd() { python3 -c 'import secrets,string; a=string.ascii_letters+string.digits; p="".join(secrets.choice(a) for _ in range(14)); print(p+secrets.choice("!@#$%&*")+secrets.choice("23456789")+"Aa9")' 2>/dev/null || echo "$(openssl rand -base64 12 | tr -d '/+=')!Aa9"; }
NEW_PWDS=()
for var in ASCLEPIO_ADMIN_PASSWORD ASCLEPIO_RODRIGO_PASSWORD; do
  cur=$(grep -E "^${var}=" .env | cut -d= -f2- || true)
  if [[ -z "$cur" ]]; then
    pw=$(gen_pwd)
    if grep -q "^${var}=" .env; then sed -i.bak "s|^${var}=.*|${var}=${pw}|" .env && rm -f .env.bak; else echo "${var}=${pw}" >> .env; fi
    NEW_PWDS+=("${var}=${pw}")
  fi
done
[[ ${#NEW_PWDS[@]} -gt 0 ]] && ok "senhas iniciais dos usuários reais geradas e salvas no .env (serão exibidas no final)"

# ---------- 2c) modelo fine-tunado (baixa da Release do GitHub se não existir localmente) ----------
MODEL_URL="${ASCLEPIO_MODEL_URL:-https://github.com/rodrigogrosa/asclepio/releases/download/v1.2.0/asclepio-med-v1.2.0.tar.gz}"
if [[ ! -f ml/models/asclepio-med/Modelfile ]]; then
  say "Modelo fine-tunado (asclepio-med) não encontrado localmente — baixando da Release (~1 GB)…"
  mkdir -p ml/models
  if curl -fL --progress-bar "$MODEL_URL" -o /tmp/asclepio-med.tar.gz && tar -xzf /tmp/asclepio-med.tar.gz -C ml/models; then
    rm -f /tmp/asclepio-med.tar.gz; ok "modelo asclepio-med baixado em ml/models/asclepio-med"
  else
    warn "não foi possível baixar o modelo fine-tunado (sem internet/asset?). A API usará o fallback llama3.1:8b; rode 'make finetune' para treinar localmente."
  fi
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
  # Persistente: qualquer `docker compose up`/`make up` futuro já inclui o Ollama (evita "Name or service not known")
  if grep -q '^COMPOSE_PROFILES=' .env; then
    grep -E '^COMPOSE_PROFILES=' .env | grep -q ollama || sed -i.bak 's|^COMPOSE_PROFILES=\(.*\)|COMPOSE_PROFILES=ollama,\1|' .env && rm -f .env.bak
  else
    echo "COMPOSE_PROFILES=ollama" >> .env
  fi
fi
# Caso contrário (host Ollama presente), remove o perfil persistido se existir só "ollama"
if curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 && grep -q '^COMPOSE_PROFILES=ollama$' .env; then
  sed -i.bak '/^COMPOSE_PROFILES=ollama$/d' .env && rm -f .env.bak
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
for spec in "API:$API_PORT" "WEB:$WEB_PORT"; do
  name=${spec%%:*}; port=${spec##*:}
  holder=$(lsof -nP -iTCP:"$port" -sTCP:LISTEN 2>/dev/null | awk 'NR==2{print $1}')
  if [[ -n "$holder" && "$holder" != com.docke* ]]; then
    warn "porta $port ($name) já está em uso no host por '$holder'. Ajuste ${name}_PORT no .env (ex.: API_PORT=8001 / WEB_PORT=3001) ou libere a porta."
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
ADMIN_PW=$(grep -E '^ASCLEPIO_ADMIN_PASSWORD=' .env | cut -d= -f2-); RODRIGO_PW=$(grep -E '^ASCLEPIO_RODRIGO_PASSWORD=' .env | cut -d= -f2-)
echo -e "  🔐 Admins reais (troca de senha + app autenticador obrigatórios no 1º acesso):"
echo -e "     admin@asclepio.fiap            senha inicial: ${ADMIN_PW}"
echo -e "     rodrigo.grosa2011@gmail.com    senha inicial: ${RODRIGO_PW}"
echo -e "     (guardadas em .env → ASCLEPIO_ADMIN_PASSWORD / ASCLEPIO_RODRIGO_PASSWORD; o .env nunca vai para o git)"
echo ""
