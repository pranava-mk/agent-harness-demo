"""
agent/llm.py — THE LLM PIECE
============================

This is the "brain." It does exactly one thing: take a list of messages
(the conversation so far) and return the model's next message.

It knows NOTHING about your files, your tools, or your data. Everything it
reacts to must be handed to it inside `messages`. That single fact is why the
rag.py and tools.py pieces exist at all.

Two backends:
  • "ollama" — talks to a local Ollama server (what Nikhil runs). No API key.
  • "stub"   — a deterministic offline fake used by the self-test, so the whole
               harness can be verified without a model installed.

Select with the PML_AGENT_BACKEND env var (default: ollama).
"""
from __future__ import annotations
import json
import os

DEFAULT_MODEL = os.environ.get("PML_AGENT_MODEL", "llama3.1:8b")
DEFAULT_EMBED_MODEL = os.environ.get("PML_AGENT_EMBED_MODEL", "nomic-embed-text")
BACKEND = os.environ.get("PML_AGENT_BACKEND", "ollama")


# ──────────────────────────────────────────────────────────────────────────────
# Ollama backend — the real thing
# ──────────────────────────────────────────────────────────────────────────────
def _to_ollama_messages(messages):
    """Convert our flat message shape back to what the Ollama client expects.

    We store tool calls as {name, arguments}; Ollama wants
    {function: {name, arguments}}. Fix those up on the way out so replayed
    history re-validates cleanly on multi-step (tool-calling) turns.
    """
    out = []
    for m in messages:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            m = dict(m)
            m["tool_calls"] = [
                {"function": {"name": tc["name"], "arguments": tc["arguments"]}}
                for tc in m["tool_calls"]
            ]
        out.append(m)
    return out


def _ollama_chat(messages, tools=None, model=None):
    import ollama  # imported lazily so the stub path needs no dependency

    resp = ollama.chat(
        model=model or DEFAULT_MODEL,
        messages=_to_ollama_messages(messages),
        tools=tools or None,
    )
    msg = resp["message"]
    # Normalise to a plain dict the rest of the code can rely on.
    out = {"role": "assistant", "content": msg.get("content", "") or ""}
    if msg.get("tool_calls"):
        out["tool_calls"] = [
            {
                "name": tc["function"]["name"],
                "arguments": tc["function"]["arguments"],
            }
            for tc in msg["tool_calls"]
        ]
    return out


def _ollama_embed(text, model=None):
    import ollama

    r = ollama.embeddings(model=model or DEFAULT_EMBED_MODEL, prompt=text)
    return r["embedding"]


# ──────────────────────────────────────────────────────────────────────────────
# Stub backend — deterministic, offline, zero dependencies.
# Enough to exercise every code path in the harness (plain reply, tool call,
# post-tool answer, embeddings) so `make selftest` works with no model present.
# ──────────────────────────────────────────────────────────────────────────────
def _stub_chat(messages, tools=None, model=None):
    # If the last message is a tool result, "summarise" it as the final answer.
    if messages and messages[-1].get("role") == "tool":
        return {"role": "assistant",
                "content": f"Based on the tool result: {messages[-1]['content']}"}

    user = next((m["content"] for m in reversed(messages)
                 if m["role"] == "user"), "").lower()

    # If tools are available and the ask looks tool-shaped, emit a tool call.
    if tools:
        for t in tools:
            fn = t["function"]
            name = fn["name"]
            if name.split("_")[-1] in user or name in user:
                # Pull the first required arg name, feed it a crude value.
                props = fn.get("parameters", {}).get("properties", {})
                arg = next(iter(props), None)
                args = {arg: user} if arg else {}
                return {"role": "assistant", "content": "",
                        "tool_calls": [{"name": name, "arguments": args}]}

    return {"role": "assistant",
            "content": f"[stub reply] You said: {user or '(nothing)'}"}


def _stub_embed(text, model=None):
    # Cheap deterministic pseudo-embedding: 64-dim bag-of-chars vector.
    vec = [0.0] * 64
    for ch in text.lower():
        vec[ord(ch) % 64] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


# ──────────────────────────────────────────────────────────────────────────────
# Public API — the rest of the app calls only these two.
# ──────────────────────────────────────────────────────────────────────────────
def chat(messages, tools=None, model=None):
    """One turn of the LLM. Returns {role, content, [tool_calls]}."""
    if BACKEND == "stub":
        return _stub_chat(messages, tools, model)
    return _ollama_chat(messages, tools, model)


def embed(text, model=None):
    """Embed one string to a vector (used by the RAG piece)."""
    if BACKEND == "stub":
        return _stub_embed(text, model)
    return _ollama_embed(text, model)
