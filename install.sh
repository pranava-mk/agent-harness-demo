#!/usr/bin/env bash
# install.sh — a GUIDED, educational one-command setup for the Agent Harness Demo.
#
# Run with nothing pre-cloned:
#   curl -fsSL https://raw.githubusercontent.com/pranava-mk/agent-harness-demo/main/install.sh | bash
#
# Unlike a silent installer, this walks you through the pieces of an agent
# harness as it builds them — explaining each, asking before each step, and
# finishing with a diagram of how everything is wired together.
#
# Two things worth knowing up front:
#   - It self-updates: if the repo is already cloned, it `git pull`s the
#     latest `main` before doing anything else, so re-running this script is
#     always safe and always gets you current.
#   - It uses absolute paths throughout (no `cd` into the project) — every
#     command below works no matter what directory you ran this from.
set -euo pipefail

REPO="https://github.com/pranava-mk/agent-harness-demo.git"
DIR_NAME="agent-harness-demo"
MODEL="llama3.1:8b"
EMBED_MODEL="nomic-embed-text"
TOTAL=6

# ── palette ─────────────────────────────────────────────────────────────────
B="$(printf '\033[1m')"; D="$(printf '\033[2m')"; R="$(printf '\033[0m')"
GRN="$(printf '\033[32m')"; YEL="$(printf '\033[33m')"; CYN="$(printf '\033[36m')"
MAG="$(printf '\033[35m')"; BLU="$(printf '\033[34m')"; RED="$(printf '\033[31m')"

hr()   { printf "%s\n" "${D}────────────────────────────────────────────────────────────${R}"; }
say()  { printf "%s\n" "${B}▸ $*${R}"; }
info() { printf "%s\n" "${D}  $*${R}"; }
good() { printf "%s\n" "${GRN}  ✓ $*${R}"; }
warn() { printf "%s\n" "${YEL}  ! $*${R}"; }

# Prompt — reads the real terminal even when piped via curl|bash.
# Default is YES (just press Enter to proceed). Non-interactive => auto-yes.
proceed() {
  local prompt="${1:-Proceed?}" reply
  if [ -r /dev/tty ]; then
    printf "%s" "  ${CYN}${prompt}${R} ${D}[Y/n]${R} " > /dev/tty
    read -r reply < /dev/tty || reply=""
  else
    reply=""   # piped with no tty — proceed automatically
  fi
  case "$reply" in [nN]*) return 1;; *) return 0;; esac
}

# Stage header: "  STEP n/TOTAL · Title"
stage() {
  echo
  hr
  printf "%s\n" "  ${MAG}${B}STEP $1/${TOTAL}${R}  ${B}·  $2${R}"
  hr
}

OS="$(uname -s)"
pkg_hint() {
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
need() {
  local tool="$1" cmd="${2:-$1}"
  if command -v "$cmd" >/dev/null 2>&1; then good "$tool is already here"; return 0; fi
  local hint; hint="$(pkg_hint "$tool")"
  warn "$tool is not installed."
  if proceed "Install it with:  $hint ?"; then eval "$hint"
  else warn "Skipped $tool — you'll need it for the demo to run."; return 1; fi
}

# ════════════════════════════════════════════════════════════════════════════
#  WELCOME
# ════════════════════════════════════════════════════════════════════════════
clear 2>/dev/null || true
echo
printf "%s\n" "  ${B}${MAG}🧩  AGENT HARNESS — guided setup${R}"
echo
info "You're about to build a complete, working AI agent — and watch each"
info "piece click into place. An agent is really just four parts:"
echo
printf "%s\n" "     ${CYN}🧠 LLM${R}   the brain — turns messages into the next message"
printf "%s\n" "     ${BLU}📚 RAG${R}   memory — finds the right knowledge to hand the brain"
printf "%s\n" "     ${YEL}🔧 Tools${R} hands — functions the brain can ask you to run"
printf "%s\n" "     ${GRN}🔁 Loop${R}  the harness — wires them together: observe→think→act"
echo
info "We'll set these up one step at a time. You approve each step."
echo
proceed "Ready to begin?" || { echo; warn "No problem — run this again anytime."; exit 0; }

# ════════════════════════════════════════════════════════════════════════════
#  STEP 1 — Prerequisites
# ════════════════════════════════════════════════════════════════════════════
stage 1 "Prerequisites  (git + uv)"
info "Every build needs ${B}git${R}${D} to fetch the code and ${B}uv${R}${D} — a fast,"
info "modern Python package/environment manager — to build an isolated"
info "environment. No system Python packages get touched."
echo
if proceed "Check (and install if missing) git & uv?"; then
  need git || true
  if command -v uv >/dev/null 2>&1; then
    good "uv is already here"
  elif proceed "Install uv now (official installer, no sudo needed)?"; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
  else
    warn "Skipped uv — the environment step below will fail without it."
  fi
else
  warn "Skipped — assuming git & uv are present."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 2 — The LLM runtime (Ollama)
# ════════════════════════════════════════════════════════════════════════════
stage 2 "🧠 The LLM  (Ollama, fully local)"
info "The ${CYN}brain${R}${D} runs on ${B}Ollama${R}${D} — a local model server. Fully offline,"
info "no API key, your data never leaves the machine. This is the piece that"
info "does the actual reasoning and decides when to reach for a tool."
echo
if command -v ollama >/dev/null 2>&1; then
  good "Ollama is already installed"
elif proceed "Set up Ollama now?"; then
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then brew install ollama
    else warn "Install it from https://ollama.com/download, then re-run."; fi
  else
    curl -fsSL https://ollama.com/install.sh | sh || warn "See https://ollama.com/download"
  fi
else
  warn "Skipped Ollama — you can still run the self-test offline."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 3 — Fetch the code (clone, or self-update if already cloned)
# ════════════════════════════════════════════════════════════════════════════
stage 3 "📥 The code  (clone, or pull latest)"
info "Resolving an ${B}absolute${R}${D} path to the repo — every command this script"
info "and the Makefile run from here on uses that full path, never a bare"
info "'cd' into the project, so it's safe to run from anywhere."
echo

# If we're already sitting inside a checked-out copy of this repo, use it.
# Otherwise clone fresh under the current directory.
REPO_ROOT=""
if [ -f "selftest.py" ] && [ -d "agent" ] && git rev-parse --show-toplevel >/dev/null 2>&1; then
  REPO_ROOT="$(git rev-parse --show-toplevel)"
  good "already inside the repo → $REPO_ROOT"
else
  REPO_ROOT="$(pwd)/$DIR_NAME"
  if [ -d "$REPO_ROOT/.git" ]; then
    good "repo already cloned → $REPO_ROOT"
  else
    say "Cloning into $REPO_ROOT…"
    git clone "$REPO" "$REPO_ROOT"
  fi
fi

# Self-update: always check for and pull the latest main before continuing,
# so re-running this script is the one command you need after any update.
if [ -d "$REPO_ROOT/.git" ]; then
  say "Checking $REPO_ROOT for updates…"
  BEFORE_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "")"
  if git -C "$REPO_ROOT" fetch --quiet origin 2>/dev/null; then
    if git -C "$REPO_ROOT" pull --quiet --ff-only 2>/dev/null; then
      AFTER_SHA="$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "")"
      if [ "$BEFORE_SHA" != "$AFTER_SHA" ]; then
        good "updated $(git -C "$REPO_ROOT" rev-parse --short "$BEFORE_SHA" 2>/dev/null || echo '?') → $(git -C "$REPO_ROOT" rev-parse --short "$AFTER_SHA")"
      else
        good "already up to date ($(git -C "$REPO_ROOT" rev-parse --short HEAD))"
      fi
    else
      warn "couldn't fast-forward (local changes in $REPO_ROOT?) — continuing with the local copy as-is"
    fi
  else
    warn "couldn't reach GitHub to check for updates — continuing with the local copy"
  fi
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 4 — The environment (uv-managed venv, absolute paths)
# ════════════════════════════════════════════════════════════════════════════
stage 4 "🔁 The environment  (uv venv + deps)"
info "Now the ${GRN}loop${R}${D} itself — the ~400 lines that wire everything together,"
info "plus the ${YEL}tools${R}${D} it can call. uv builds an isolated environment at"
info "${B}$REPO_ROOT/.venv${R}${D} — nothing touches your system Python."
echo
PY="$REPO_ROOT/.venv/bin/python3"
if proceed "Build the environment with uv?"; then
  if ! command -v uv >/dev/null 2>&1; then
    warn "uv isn't on PATH — can't build the environment. Install uv and re-run."
  else
    say "Creating venv at $REPO_ROOT/.venv…"
    uv venv "$REPO_ROOT/.venv" --quiet
    say "Installing dependencies…"
    uv pip install --quiet --python "$PY" -r "$REPO_ROOT/requirements.txt"
    good "environment ready → $PY"
  fi
else
  warn "Skipped — the demo can't run without the environment."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 5 — The models (brain + memory)
# ════════════════════════════════════════════════════════════════════════════
stage 5 "📚 The models  (reasoning + embeddings)"
info "Two models power two pieces:"
info "  • ${B}${MODEL}${R}${D} — the ${CYN}brain${R}${D} (chat, reasoning, tool-calling)"
info "  • ${B}${EMBED_MODEL}${R}${D} — the ${BLU}embedder${R}${D} that turns your docs into"
info "    vectors so RAG can find the right ones. First pull takes a few minutes."
echo
if command -v ollama >/dev/null 2>&1 && proceed "Pull the local models now?"; then
  if ! curl -s http://localhost:11434/api/tags >/dev/null 2>&1; then
    info "starting the Ollama server…"; (ollama serve >/dev/null 2>&1 &); sleep 3
  fi
  say "Pulling ${MODEL} (the brain)…"
  ollama pull "$MODEL"       || warn "couldn't pull $MODEL — pull it manually later"
  say "Pulling ${EMBED_MODEL} (the embedder)…"
  ollama pull "$EMBED_MODEL" || warn "couldn't pull $EMBED_MODEL — pull it manually later"
  good "models ready"
else
  warn "Skipped model pull — low-spec? See the README for tiny-model options."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 6 — Verify the wiring
# ════════════════════════════════════════════════════════════════════════════
stage 6 "✅ Verify  (does it all connect?)"
info "Before we celebrate, let's prove every piece is wired correctly. The"
info "self-test runs the whole harness on a built-in ${B}offline fake${R}${D} backend —"
info "so it passes with or without a model, checking tools, RAG, PDF parsing"
info "and the loop."
echo
if proceed "Run the self-test now?"; then
  if [ -x "$PY" ]; then
    PML_AGENT_BACKEND=stub "$PY" "$REPO_ROOT/selftest.py" || warn "self-test reported an issue (see above)"
  else
    warn "no environment built yet (step 4 was skipped) — can't run the self-test."
  fi
else
  warn "Skipped — you can run it anytime (see the command below)."
fi

# ════════════════════════════════════════════════════════════════════════════
#  DONE — the wiring diagram
# ════════════════════════════════════════════════════════════════════════════
echo; echo
hr
printf "%s\n" "  ${GRN}${B}✅  YOUR AGENT IS ASSEMBLED${R}"
hr
echo
printf "%s\n" "  ${D}Here's how the pieces are now plugged together:${R}"
echo
printf '%s\n' "        ${B}you${R} ${D}│${R} \"what is a harness?\"  ·  \"what is 19*23?\"  ·  📄 upload a PDF"
printf '%s\n' "         ${D}▼${R}"
printf '%s\n' "   ${GRN}┌───────────────────────────────────────────────────┐${R}"
printf '%s\n' "   ${GRN}│${R}  ${GRN}${B}🔁 THE LOOP${R}  ${D}(the harness — runs the cycle)${R}      ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}                                                   ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}   observe ──▶ think ──▶ act ──▶ repeat ↺           ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}      ${BLU}│${R}         ${CYN}│${R}        ${YEL}│${R}                     ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}      ${BLU}▼${R}         ${CYN}▼${R}        ${YEL}▼${R}                     ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}  ${BLU}┌───────┐${R} ${CYN}┌──────┐${R} ${YEL}┌───────┐${R}               ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}  ${BLU}│📚 RAG │${R} ${CYN}│🧠 LLM│${R} ${YEL}│🔧 Tool│${R}               ${GRN}│${R}"
printf '%s\n' "   ${GRN}│${R}  ${BLU}└───────┘${R} ${CYN}└──────┘${R} ${YEL}└───────┘${R}               ${GRN}│${R}"
printf '%s\n' "   ${GRN}└───────────────────────────────────────────────────┘${R}"
echo
printf '%s\n' "   ${BLU}📚 RAG${R}  ${D}finds relevant knowledge and feeds it into context${R}"
printf '%s\n' "   ${CYN}🧠 LLM${R}  ${D}reads everything, decides: answer, or call a tool${R}"
printf '%s\n' "   ${YEL}🔧 Tool${R} ${D}your code runs it; the result goes back to the LLM${R}"
printf '%s\n' "   ${GRN}🔁 Loop${R} ${D}repeats until the LLM replies in plain text → you${R}"
echo
info "That's the whole trick: the LLM only ever knows what the loop puts in"
info "front of it. Everything else is context engineering + this dispatch loop."
info "The web UI also has a 📄 PDF upload button — drop in a document and ask"
info "questions about it; it's chunked, embedded and indexed live, on the spot."
echo
hr
say "Start talking to your agent (absolute paths — works from anywhere):"
printf "%s\n" "   ${B}$PY $REPO_ROOT/web.py${R}"
info "opens a browser chat that shows RAG + tool calls live, with a PDF upload button"
echo
info "Prefer the terminal?    $PY $REPO_ROOT/chat.py"
info "Offline / no model?     PML_AGENT_BACKEND=stub $PY $REPO_ROOT/selftest.py"
info "Or with make (same absolute-path approach, from any directory):"
info "    make -C $REPO_ROOT web"
echo
info "Re-running this script any time self-updates the repo and environment:"
printf "%s\n" "   ${B}curl -fsSL https://raw.githubusercontent.com/pranava-mk/agent-harness-demo/main/install.sh | bash${R}"
echo
