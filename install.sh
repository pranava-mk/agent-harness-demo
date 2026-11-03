#!/usr/bin/env bash
# install.sh — one-command setup for the Agent Harness Demo.
#
# Run with nothing pre-cloned:
#   curl -fsSL https://raw.githubusercontent.com/pranava-mk/agent-harness-demo/main/install.sh | bash
#
# It will: check deps (git, python3, ollama) and offer to install any missing
# ones (asking first), clone the repo, set up a venv, pull a small local model,
# run the self-test, and leave you one command away from chatting.
set -euo pipefail

REPO="https://github.com/pranava-mk/agent-harness-demo.git"
DIR="agent-harness-demo"
MODEL="llama3.1:8b"
EMBED_MODEL="nomic-embed-text"
BOLD="$(printf '\033[1m')"; DIM="$(printf '\033[2m')"; GRN="$(printf '\033[32m')"; YEL="$(printf '\033[33m')"; RST="$(printf '\033[0m')"

say()  { printf "%s\n" "${BOLD}▸ $*${RST}"; }
info() { printf "%s\n" "${DIM}  $*${RST}"; }
warn() { printf "%s\n" "${YEL}  $*${RST}"; }

# Read y/n even when the script itself is piped from curl (reads the terminal).
ask() {
  local prompt="$1" reply
  if [ -r /dev/tty ]; then read -r -p "  $prompt [y/N] " reply </dev/tty || reply=""
  else reply=""; fi
  case "$reply" in [yY]*) return 0;; *) return 1;; esac
}

OS="$(uname -s)"
pkg_hint() { # $1 = tool
  case "$OS" in
    Darwin) echo "brew install $1";;
    Linux)
      if   command -v apt >/dev/null;    then echo "sudo apt install -y $1"
      elif command -v pacman >/dev/null; then echo "sudo pacman -S --noconfirm $1"
      elif command -v dnf >/dev/null;    then echo "sudo dnf install -y $1"
      else echo "(install $1 with your package manager)"; fi;;
    *) echo "(install $1)";;
  esac
}

need() { # ensure a command exists, offering to install it
  local tool="$1" cmd="${2:-$1}"
  if command -v "$cmd" >/dev/null 2>&1; then info "$tool found"; return 0; fi
  local hint; hint="$(pkg_hint "$tool")"
  warn "$tool is not installed."
  if ask "Install it now with:  $hint ?"; then
    eval "$hint"
  else
    warn "Skipping $tool — you'll need to install it yourself for the demo to run."
    return 1
  fi
}

echo
say "Agent Harness Demo — setup"
echo

# ── 1. prerequisites ──────────────────────────────────────────────────────────
need git || true
need python3 python3 || true

# Ollama has its own installer; handle it specially.
if command -v ollama >/dev/null 2>&1; then
  info "ollama found"
else
  warn "ollama (the local LLM runtime) is not installed."
  if [ "$OS" = "Darwin" ]; then
    if ask "Install ollama via Homebrew (brew install ollama)?"; then brew install ollama
    else warn "Get it from https://ollama.com/download then re-run."; fi
  else
    if ask "Install ollama via the official script (curl https://ollama.com/install.sh | sh)?"; then
      curl -fsSL https://ollama.com/install.sh | sh
    else warn "Get it from https://ollama.com/download then re-run."; fi
  fi
fi

# ── 2. clone (skip if already inside the repo) ────────────────────────────────
if [ -f "selftest.py" ] && [ -d "agent" ]; then
  info "already inside the repo"
else
  if [ -d "$DIR" ]; then info "repo already cloned → $DIR"; else
    say "Cloning the repo"; git clone --depth 1 "$REPO" "$DIR"
  fi
  cd "$DIR"
fi

# ── 3. python venv + deps ─────────────────────────────────────────────────────
say "Setting up Python environment"
python3 -m venv .venv
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q --upgrade pip
pip install -q -r requirements.txt
info "dependencies installed"

# ── 4. pull a small local model (if ollama is here and running) ───────────────
if command -v ollama >/dev/null 2>&1; then
  say "Pulling local models (first time only — a few minutes)"
  # make sure the ollama server is up
  if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    info "starting ollama server in the background"
    (ollama serve >/dev/null 2>&1 &) ; sleep 3
  fi
  ollama pull "$MODEL"       || warn "could not pull $MODEL — pull it manually later"
  ollama pull "$EMBED_MODEL" || warn "could not pull $EMBED_MODEL — pull it manually later"
else
  warn "ollama not available — skipping model pull."
fi

# ── 5. self-test (offline, always safe) ───────────────────────────────────────
say "Running the self-test (offline, no model needed)"
PML_AGENT_BACKEND=stub python3 selftest.py

# ── 6. done ───────────────────────────────────────────────────────────────────
echo
printf "%s\n" "${GRN}${BOLD}✅ Ready.${RST}"
echo
say "Start chatting with your agent:"
info "cd ${DIR}  &&  . .venv/bin/activate  &&  make chat"
echo
info "No model / offline? Try the harness logic with:  make selftest"
echo
