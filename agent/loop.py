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

        # 1. OBSERVE — augment the user's turn with retrieved knowledge.
        content = user_text
        if self.knowledge:
            ctx = self.knowledge.context_for(user_text)
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
                return reply["content"]  # plain answer → done

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
