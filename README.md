<div align="center">

# 🧩 Agent Harness Demo

**A complete AI agent you can read in one sitting and run in one command.**

Local LLM · retrieval (RAG) · tool-calling · a chat loop — ~400 lines of plain
Python, no framework, no cloud, no API key.

[Quick start](#-quick-start) · [The four pieces](#-the-four-pieces) · [How the loop works](#-how-the-agent-loop-works) · [Concepts](#-concepts-cheat-sheet)

</div>

---

## Why this exists

Every "AI agent" — a coding assistant, a support bot, a research tool — is the
same small idea wearing different clothes: **an LLM inside a loop that can pull
in knowledge and call tools.** This repo strips that idea down to its skeleton
so you can *see* it. Each file owns exactly one of the four pieces, and every
piece is verified by an offline self-test.

Runs fully local on a Mac via [Ollama](https://ollama.com) — your data never
leaves the machine.

## 🚀 Quick start

**One command, nothing pre-cloned:**

```bash
curl -fsSL https://raw.githubusercontent.com/pranava-mk/agent-harness-demo/main/install.sh | bash
```

It checks for `git` / `uv` / `ollama` (offering to install anything missing —
it asks first), clones the repo (or **self-updates** it with `git pull` if
you've already got it — just re-run the same command any time), builds an
isolated environment with [`uv`](https://github.com/astral-sh/uv), pulls a
small local model, and runs the self-test. Every command it prints uses an
**absolute path** — nothing relies on `cd`-ing into the project first. Then:

```bash
make -C agent-harness-demo web
```

This opens a **browser chat** that shows, live, what the agent does under the
hood — which knowledge it retrieved (RAG) and which tools it called — before
each answer. There's also a **📄 PDF upload button** right in the chat: drop
in a document and it's parsed, chunked, embedded and indexed on the spot,
with every pipeline step shown live — then you can ask questions about it
(real RAG, not a demo fake). Prefer the terminal? `make -C agent-harness-demo chat`
runs the same agent as a CLI.

**No model / want to see it work offline right now?**

```bash
make -C agent-harness-demo selftest      # exercises every piece with a built-in fake backend
```

## 🧱 The four pieces

| Piece | File | What it owns |
|---|---|---|
| 🧠 **LLM** | [`agent/llm.py`](agent/llm.py) | The brain. Takes messages → returns the next message. Knows nothing else. |
| 📚 **RAG** | [`agent/rag.py`](agent/rag.py) | Embeds `knowledge/` into vectors; retrieves the chunks most relevant to a question. |
| 🔧 **Tools** | [`agent/tools.py`](agent/tools.py) | Functions the LLM can *ask* to run (calculate, date, word-count). You run them, not the model. |
| 🔁 **Loop** | [`agent/loop.py`](agent/loop.py) | The harness: wires the three together and runs observe→think→act→repeat. |
| 📄 **PDF parsing** | [`agent/pdf_extract.py`](agent/pdf_extract.py) | Stdlib-only PDF text extraction (no PyPDF2/pdfplumber) — handles the common case including browser/LibreOffice-generated CID-font PDFs. Feeds `add_document` for live uploads. |
| 💬 **Chat** | [`web.py`](web.py) · [`chat.py`](chat.py) | The human-facing UI — a browser chat (shows RAG + tool steps live, plus live PDF upload) or a terminal REPL. Thin on purpose; all intelligence lives in `agent/`. |

## 🔁 How the agent loop works

```
            ┌─────────────────────────────────────────────┐
            │                                             │
 you ──▶ OBSERVE ──▶ THINK ──▶ has tool call? ──yes──▶ ACT ┘
 ask    (RAG pulls   (LLM         │                  (run the
         relevant     decides)    no                  tool, feed
         knowledge)                │                  result back)
                                   ▼
                              final answer ──▶ you
```

1. **Observe** — retrieve knowledge relevant to your question, inject it into context.
2. **Think** — the LLM decides: answer directly, or call a tool.
3. **Act** — if it chose a tool, *your code* runs it and feeds the result back.
4. **Repeat** — until the LLM replies in plain text. (A step cap prevents runaways.)

The LLM only ever "knows" what the loop put in front of it. That's the whole
trick — **context engineering + a dispatch loop.**

## 🧪 Try these once it's running

```
you ▸ what is a harness?          # → answered from knowledge/ via RAG
you ▸ what is 1287 * 43?          # → the LLM calls the calculate tool
you ▸ what time is it?            # → calls the current_datetime tool
```

Run `make chatv` (verbose) to watch retrieval and tool calls happen live.
In the **web UI** (`make web`) every answer already shows these steps inline —
a 📚 RAG tag and a 🔧 TOOL tag appear above each reply, so you can see exactly
what the agent did.

## 🛠️ Extend it

- **Add a tool:** write a function in `agent/tools.py`, decorate with `@tool(...)`. Done — the LLM can now use it.
- **Add knowledge:** drop any `.md`/`.txt` file into `knowledge/`. It's indexed on next run.
- **Swap the model:** `PML_AGENT_MODEL=llama3.1:70b make chat`
- **Swap the backend:** `PML_AGENT_BACKEND=stub` (offline fake) — used by the self-test.

### Models

Out of the box the installer pulls a capable local setup (great on a 16 GB Mac
with Metal, or any machine with ~6 GB free for inference):

| Role | Default model | Size |
|---|---|---|
| Chat / reasoning / tools | `llama3.1:8b` | ~4.7 GB |
| Embeddings (RAG) | `nomic-embed-text` | ~275 MB |

**On a weak / CPU-only box?** Drop to tiny models (verified on an 8-core i5 /
16 GB / no GPU) and shrink the RAG chunk to fit a small embedder:

```bash
ollama pull qwen2.5:0.5b      # ~400 MB chat model
ollama pull all-minilm        # ~45 MB embedding model

PML_AGENT_MODEL=qwen2.5:0.5b \
PML_AGENT_EMBED_MODEL=all-minilm \
PML_AGENT_CHUNK_WORDS=120 \
make -C agent-harness-demo chat
```

`PML_AGENT_EMBED_MODEL` and `PML_AGENT_CHUNK_WORDS` let you match the RAG chunk
size to a small embedder's context limit (all-minilm maxes ~256 tokens).

## 📖 Concepts cheat-sheet

Short, plain-language definitions live in [`knowledge/agent-concepts.md`](knowledge/agent-concepts.md)
— and because that file *is* the agent's knowledge base, the agent can answer
questions about them itself. Covered: LLM, context window, agent, agent loop,
tool calling, harness, RAG, embeddings, **MCP**, and **skills**.

## Requirements

- **[uv](https://github.com/astral-sh/uv)** to build the isolated Python environment (the installer sets it up)
- **[Ollama](https://ollama.com)** for the real local LLM (the installer sets it up)
- One Python dependency (`ollama` client). The agent loop, RAG, tools and chat
  are pure standard library — deliberately, so nothing hides the mechanism.

## Project layout

```
agent-harness-demo/
├── agent/
│   ├── llm.py       # 🧠 LLM backend (ollama | offline stub)
│   ├── rag.py       # 📚 knowledge retrieval (+ live PDF-upload indexing)
│   ├── tools.py     # 🔧 tool registry + demo tools
│   ├── pdf_extract.py # 📄 stdlib-only PDF text extraction
│   └── loop.py      # 🔁 the agent loop (the harness)
├── knowledge/
│   └── agent-concepts.md   # the RAG corpus (also the cheat-sheet)
├── examples/demo.py # three scripted questions, end-to-end
├── web.py          # 💬 the browser chat UI (shows RAG + tool steps live)
├── chat.py          # 💬 the terminal chat REPL
├── selftest.py      # ✅ verifies every piece offline
├── install.sh       # one-command guided setup
└── Makefile         # make web | chat | selftest | demo
```

## License

MIT — do anything, no warranty.
