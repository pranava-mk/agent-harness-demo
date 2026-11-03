#!/usr/bin/env bash
# install.sh — a GUIDED, educational one-command setup for the Agent Harness Demo.
#
# Run with nothing pre-cloned:
#   curl -fsSL https://raw.githubusercontent.com/pranava-mk/agent-harness-demo/main/install.sh | bash
#
# Unlike a silent installer, this walks you through the FOUR pieces of an agent
# harness as it builds them — explaining each, asking before each step, and
# finishing with a diagram of how everything is wired together.
set -euo pipefail

REPO="https://github.com/pranava-mk/agent-harness-demo.git"
DIR="agent-harness-demo"
MODEL="llama3.1:8b"
EMBED_MODEL="nomic-embed-text"
TOTAL=5

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

typefx() { printf "%s\n" "$*"; }   # placeholder hook (kept simple/fast)

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
stage 1 "Prerequisites  (git + python)"
info "Every build needs a couple of basics: ${B}git${R}${D} to fetch the code and"
info "${B}python3${R}${D} to run it. Let's make sure they're present."
echo
if proceed "Check (and install if missing) git & python3?"; then
  need git || true
  need python3 python3 || true
else
  warn "Skipped — assuming git & python3 are present."
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
  warn "Skipped Ollama — you can still run 'make selftest' offline."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 3 — The harness code (clone + environment)
# ════════════════════════════════════════════════════════════════════════════
stage 3 "🔁 The harness  (code + environment)"
info "Now the ${GRN}loop${R}${D} itself — the ~400 lines that wire everything together,"
info "plus the ${YEL}tools${R}${D} it can call. We'll fetch the code and create an isolated"
info "Python environment so nothing touches your system packages."
echo
if proceed "Fetch the code and build the environment?"; then
  if [ -f "selftest.py" ] && [ -d "agent" ]; then
    good "already inside the repo"
  else
    if [ -d "$DIR" ]; then good "repo already cloned → $DIR"
    else say "Cloning…"; git clone --depth 1 "$REPO" "$DIR"; fi
    cd "$DIR"
  fi
  say "Creating virtual environment + installing dependencies…"
  python3 -m venv .venv
  # shellcheck disable=SC1091
  . .venv/bin/activate
  pip install -q --upgrade pip
  pip install -q -r requirements.txt
  good "environment ready"
else
  warn "Skipped — the demo can't run without the code."
fi

# ════════════════════════════════════════════════════════════════════════════
#  STEP 4 — The models (brain + memory)
# ════════════════════════════════════════════════════════════════════════════
stage 4 "📚 The models  (reasoning + embeddings)"
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
#  STEP 5 — Verify the wiring
# ════════════════════════════════════════════════════════════════════════════
stage 5 "✅ Verify  (does it all connect?)"
info "Before we celebrate, let's prove every piece is wired correctly. The"
info "self-test runs the whole harness on a built-in ${B}offline fake${R}${D} backend —"
info "so it passes with or without a model, checking tools, RAG and the loop."
echo
if proceed "Run the self-test now?"; then
  PML_AGENT_BACKEND=stub python3 selftest.py || warn "self-test reported an issue (see above)"
else
  warn "Skipped — you can run it anytime with 'make selftest'."
fi

# ════════════════════════════════════════════════════════════════════════════
#  DONE — the wiring diagram
# ════════════════════════════════════════════════════════════════════════════
echo; echo
hr
printf "%s\n" "  ${GRN}${B}✅  YOUR AGENT IS ASSEMBLED${R}"
hr
echo
printf "%s\n" "  ${D}Here's how the four pieces are now plugged together:${R}"
echo
printf '%s\n' "        ${B}you${R} ${D}│${R} \"what is a harness?\"  ·  \"what is 19*23?\""
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
echo
hr
say "Start talking to your agent:"
printf "%s\n" "   ${B}cd ${DIR}  &&  . .venv/bin/activate  &&  make web${R}"
info "opens a browser chat that shows RAG + tool calls live as it answers"
echo
info "Prefer the terminal?    make chat            (same agent, CLI)"
info "Offline / no model?     make selftest        (verifies the wiring)"
echo
