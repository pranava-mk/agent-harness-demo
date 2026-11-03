"""
examples/demo.py — three scripted questions showing each piece in action.
Run after setup (needs ollama + a pulled model):  make demo
Offline?  PML_AGENT_BACKEND=stub python3 examples/demo.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from agent import Agent

QUESTIONS = [
    ("RAG / knowledge", "In one sentence, what is an agent harness?"),
    ("Tool calling",    "What is 1287 * 43?"),
    ("Tool calling",    "What's today's date?"),
]


def main():
    agent = Agent()
    for tag, q in QUESTIONS:
        print(f"\n── {tag} " + "─" * (40 - len(tag)))
        print(f"  Q: {q}")
        print(f"  A: {agent.ask(q, verbose=True)}")
    print()


if __name__ == "__main__":
    main()
