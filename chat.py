"""
chat.py — THE CHAT INTERFACE PIECE
==================================

The human-facing surface. A simple REPL: type a message, the agent runs its
full loop (RAG + tools + LLM), you see the answer. This is deliberately thin —
all the intelligence lives in agent/. Swap this file for a web UI or a Slack bot
and nothing else has to change.

Run:  python chat.py          (normal)
      python chat.py -v       (verbose: shows retrieval + tool calls)
"""
import sys

from agent import Agent


def main():
    verbose = "-v" in sys.argv or "--verbose" in sys.argv
    print("\n  🤖  Agent Harness Demo")
    print("  ─────────────────────")
    print("  Local LLM + RAG + tools + this chat loop.")
    print("  Try:  'what is a harness?'  ·  'what is 19*23?'  ·  'what time is it?'")
    print("  Ctrl-C or 'exit' to quit.", "(verbose on)" if verbose else "", "\n")

    agent = Agent()
    while True:
        try:
            user = input("  you ▸ ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  bye 👋\n")
            return
        if user.lower() in {"exit", "quit"}:
            print("  bye 👋\n")
            return
        if not user:
            continue
        answer = agent.ask(user, verbose=verbose)
        print(f"\n  bot ▸ {answer}\n")


if __name__ == "__main__":
    main()
