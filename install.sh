#!/usr/bin/env bash
# =====================================================================
#  ASCLÉPIO — instalador de 1 linha
#
#    curl -fsSL https://raw.githubusercontent.com/rodrigogrosa/asclepio/main/install.sh | bash
#
#  O que faz: verifica/instala pré-requisitos (git, Docker, Ollama), clona o repositório
#  (ou atualiza se já existir), e roda o bootstrap (scripts/bootstrap.sh) que sobe tudo em Docker.
#  Variáveis opcionais: ASCLEPIO_DIR (destino, padrão ~/asclepio) · ASCLEPIO_REPO · ASCLEPIO_BRANCH
#                       ASCLEPIO_FULL=1 (sobe também LiteLLM + Langfuse) · ASCLEPIO_NO_OLLAMA=1 (não instala Ollama)
#  Suporta macOS (Homebrew) e Linux (apt/dnf + script oficial do Docker). Windows: use WSL2 (Ubuntu) e rode o mesmo comando.
# =====================================================================
set -euo pipefail

REPO="${ASCLEPIO_REPO:-https://github.com/rodrigogrosa/asclepio.git}"
BRANCH="${ASCLEPIO_BRANCH:-main}"
DIR="${ASCLEPIO_DIR:-$HOME/asclepio}"
PINK='\033[1;35m'; GRN='\033[1;32m'; YEL='\033[1;33m'; RED='\033[1;31m'; NC='\033[0m'
say()  { echo -e "${PINK}▶${NC} $*"; }
ok()   { echo -e "${GRN}✔${NC} $*"; }
warn() { echo -e "${YEL}!${NC} $*"; }
die()  { echo -e "${RED}✖${NC} $*"; exit 1; }

OS="$(uname -s)"
echo -e "${PINK}"
echo "  ASCLÉPIO — Assistente Clínico Inteligente · instalador"
echo -e "${NC}"

# ---------- helpers de instalação ----------
need_sudo() { if [[ $EUID -ne 0 ]] && command -v sudo >/dev/null; then echo sudo; fi; }

install_brew() {
  if ! command -v brew >/dev/null; then
    say "Instalando Homebrew (gerenciador de pacotes do macOS)…"
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv 2>/dev/null || /usr/local/bin/brew shellenv)"
  fi
}

ensure_git() {
  if command -v git >/dev/null; then ok "git $(git --version | awk '{print $3}')"; return; fi
  say "Instalando git…"
  case "$OS" in
    Darwin) xcode-select --install 2>/dev/null || true; install_brew; brew install git ;;
    Linux)  S=$(need_sudo); if command -v apt-get >/dev/null; then $S apt-get update -y && $S apt-get install -y git curl; elif command -v dnf >/dev/null; then $S dnf install -y git curl; else die "instale o git manualmente"; fi ;;
  esac
}

ensure_docker() {
  if command -v docker >/dev/null && docker info >/dev/null 2>&1; then ok "Docker $(docker --version | awk '{print $3}' | tr -d ,) em execução"; return; fi
  case "$OS" in
    Darwin)
      if ! command -v docker >/dev/null; then
        install_brew; say "Instalando Docker Desktop (brew install --cask docker)…"; brew install --cask docker
      fi
      say "Abrindo o Docker Desktop (na primeira vez aceite os termos na janela que abrir)…"; open -a Docker || true
      ;;
    Linux)
      if ! command -v docker >/dev/null; then
        say "Instalando Docker Engine (script oficial get.docker.com)…"
        curl -fsSL https://get.docker.com | $(need_sudo) sh
        $(need_sudo) usermod -aG docker "$USER" 2>/dev/null || true
        warn "Você foi adicionado ao grupo docker; pode ser necessário sair e entrar de novo (ou rodar com sudo) se aparecer 'permission denied'."
      fi
      $(need_sudo) systemctl enable --now docker 2>/dev/null || true
      ;;
    *) die "Sistema $OS não suportado automaticamente. No Windows, use WSL2 (Ubuntu) com Docker Desktop e rode este script dentro do WSL." ;;
  esac
  say "Aguardando o Docker iniciar…"
  for i in $(seq 1 60); do docker info >/dev/null 2>&1 && { ok "Docker pronto"; return; }; sleep 3; done
  die "Docker não respondeu. Abra o Docker Desktop manualmente e rode de novo: curl -fsSL .../install.sh | bash"
}

ensure_ollama() {
  [[ "${ASCLEPIO_NO_OLLAMA:-0}" == "1" ]] && { warn "Ollama não será instalado (ASCLEPIO_NO_OLLAMA=1) — será usado em container."; return; }
  if command -v ollama >/dev/null; then ok "Ollama $(ollama --version 2>/dev/null | awk '{print $NF}')"; else
    case "$OS" in
      Darwin) install_brew; say "Instalando Ollama (usa a GPU Metal — muito mais rápido que em container)…"; brew install ollama ;;
      Linux)  say "Instalando Ollama (script oficial)…"; curl -fsSL https://ollama.com/install.sh | sh ;;
    esac
  fi
  if ! curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1; then
    say "Iniciando o servidor do Ollama…"
    case "$OS" in
      Darwin) (brew services start ollama >/dev/null 2>&1 || (nohup ollama serve >/dev/null 2>&1 &)) ;;
      Linux)  ($(need_sudo) systemctl start ollama 2>/dev/null || (nohup ollama serve >/dev/null 2>&1 &)) ;;
    esac
    for i in $(seq 1 20); do curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 && break; sleep 2; done
  fi
  curl -fsS http://localhost:11434/api/tags >/dev/null 2>&1 && ok "Ollama em execução" || warn "Ollama não respondeu; o bootstrap usará Ollama em container."
}

# ---------- 1) pré-requisitos ----------
say "Verificando pré-requisitos"
command -v curl >/dev/null || die "curl é necessário"
ensure_git
ensure_docker
ensure_ollama
command -v make >/dev/null || warn "'make' não encontrado — tudo bem, o instalador chama o bootstrap diretamente (para usar 'make ...' depois, instale build-essential/Xcode CLT)."

# ---------- 2) código ----------
if [[ -d "$DIR/.git" ]]; then
  say "Repositório já existe em $DIR — atualizando (git pull)…"
  git -C "$DIR" pull --ff-only || warn "não foi possível atualizar (alterações locais?); seguindo com a versão atual"
else
  say "Clonando $REPO (branch $BRANCH) em $DIR…"
  git clone --branch "$BRANCH" --depth 1 "$REPO" "$DIR"
fi
cd "$DIR"

# ---------- 3) sobe tudo ----------
if [[ "${ASCLEPIO_FULL:-0}" == "1" ]]; then
  LANGFUSE_ENABLED=true ./scripts/bootstrap.sh --profile observability
else
  ./scripts/bootstrap.sh
fi

echo -e "${GRN}Instalação concluída.${NC} Diretório: $DIR  ·  Comandos úteis: cd $DIR && make help"
