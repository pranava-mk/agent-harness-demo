"""Makes `agent/` a package. See each module's docstring for the piece it owns:
  llm.py   — the LLM brain (Ollama or offline stub)
  rag.py   — the knowledge/retrieval piece
  tools.py — the tool-calling piece
  loop.py  — the agent loop that wires them together
"""
from .loop import Agent

__all__ = ["Agent"]
