"""
agent/loop.py — THE AGENT LOOP (the harness itself)
===================================================

This is what makes it an "agent" rather than a chatbot. The loop:

    observe → think → act → repeat

  1. OBSERVE  pull relevant knowledge (RAG) for the user's question and inject it
  2. THINK    ask the LLM what to do next, giving it the tool schemas
  3. ACT      if the LLM asked for a tool, run it and feed the result back
  4. REPEAT   until the LLM answers in plain text (no more tool calls)

Everything the model "knows" in a turn is whatever this loop put into `messages`.
That's the entire trick behind agents — context engineering plus a dispatch loop.
"""
from __future__ import annotations

import os

from . import tools
from .llm import chat
from .rag import Knowledge

SYSTEM_PROMPT = (
    "You are a concise, helpful assistant. "
    "Use the provided tools when they help answer accurately. "
    "When 'Relevant knowledge' is provided, prefer it over your own guesses "
    "and say so if the knowledge doesn't cover the question."
)

MAX_STEPS = 5  # safety rail so a tool-call loop can never run forever

# Cap on how many user turns of conversation history we keep. Without this,
# a long-running session (e.g. the web UI, whose Agent instance lives for
# the whole server process) accumulates every message ever sent -- forever
# growing prompts, slower calls, and a subtle correctness trap: old RAG
# injections and tool results linger in context long after they're relevant
# (we hit this directly -- deleting an uploaded PDF didn't stop the LLM from
# still "knowing" a fact from it, because the earlier turn where it was
# injected was still sitting in self.messages). Override via
# PML_AGENT_MAX_HISTORY_TURNS if you want a bigger/smaller window.
MAX_HISTORY_TURNS = int(os.environ.get("PML_AGENT_MAX_HISTORY_TURNS", "6"))


class Agent:
    def __init__(self, use_rag=True):
        self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.knowledge = Knowledge().build() if use_rag else None

    def ask(self, user_text, verbose=False, trace=None):
        """Run one full observe→think→act→repeat cycle, return the final answer.

        If `trace` is a list, structured step events are appended to it
        (used by the web UI to show what the agent did): each is a dict like
        {"kind": "rag"|"tool"|"result", ...}.
        """
        def emit(kind, **data):
            if trace is not None:
                trace.append({"kind": kind, **data})

        try:
            # 1. OBSERVE — augment the user's turn with retrieved knowledge.
            content = user_text
            if self.knowledge:
                score_steps = [] if trace is not None else None
                ctx = self.knowledge.context_for(user_text, trace_steps=score_steps)
                if trace is not None and score_steps:
                    # Surface the fine-grained "query embedded -> compared against
                    # each chunk -> scored" steps BEFORE the summary, so a learner
                    # sees the actual retrieval mechanism, not just its outcome.
                    for s in score_steps:
                        emit(s.pop("kind"), **s)
                if ctx:
                    content = f"{ctx}\n\nQuestion: {user_text}"
                    n = ctx.count("---") + 1
                    if verbose:
                        print(f"  ⟐ injected {n} knowledge chunk(s)")
                    emit("rag", chunks=n)
            self.messages.append({"role": "user", "content": content})

            # 2–4. THINK → ACT → REPEAT
            for step in range(MAX_STEPS):
                reply = chat(self.messages, tools=tools.schemas())
                self.messages.append(reply)

                calls = reply.get("tool_calls")
                if not calls:
                    answer = (reply.get("content") or "").strip()
                    if answer:
                        return answer
                    # Degenerate turn: no tool call AND empty content. Some small
                    # models do this when tool schemas are attached — they produce
                    # neither. Retry once WITHOUT tools to force a plain answer so
                    # the user never sees a blank reply.
                    if verbose:
                        print("  ↻ empty reply with tools — retrying without tools")
                    retry = chat(self.messages)
                    answer = (retry.get("content") or "").strip()
                    return answer or "(the model returned an empty response — try rephrasing, or use a larger model)"

                for call in calls:
                    if verbose:
                        print(f"  ⚙ tool: {call['name']}({call['arguments']})")
                    result = tools.run(call["name"], call["arguments"])
                    if verbose:
                        print(f"    → {result}")
                    emit("tool", name=call["name"], arguments=call["arguments"],
                         result=result)
                    self.messages.append({"role": "tool",
                                          "name": call["name"],
                                          "content": result})

            return "(stopped: reached max reasoning steps)"
        finally:
            # Runs on every exit path (plain answer, tool-call answer, empty-
            # reply fallback, or the max-steps bailout) -- trims BEFORE the
            # next call ever sees a too-long history.
            self._trim_history()

    def _trim_history(self):
        """Keep the system prompt plus only the most recent MAX_HISTORY_TURNS
        user turns (and everything that followed each, e.g. tool calls/
        results) — drops whole turns from the oldest end, never mid-turn,
        so a dangling tool-result message (with no matching assistant
        tool-call before it) can never end up at the front of history."""
        if not self.messages:
            return
        has_system = self.messages[0]["role"] == "system"
        head = self.messages[:1] if has_system else []
        rest = self.messages[len(head):]
        user_idxs = [i for i, m in enumerate(rest) if m["role"] == "user"]
        if len(user_idxs) <= MAX_HISTORY_TURNS:
            return
        cutoff = user_idxs[-MAX_HISTORY_TURNS]
        self.messages = head + rest[cutoff:]
