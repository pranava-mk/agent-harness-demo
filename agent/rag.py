"""
agent/rag.py — THE RAG (KNOWLEDGE) PIECE
========================================

The LLM wasn't trained on your private notes. RAG (Retrieval-Augmented
Generation) fixes that WITHOUT retraining: we turn your documents into vectors,
and at question time we find the chunks most similar to the question and paste
them into the LLM's context.

Flow:
  1. Load every .md/.txt file in knowledge/ and split into chunks.
  2. Embed each chunk once (via llm.embed) -> an in-memory vector index.
  3. search(question) embeds the question and returns the top-k closest chunks.

Zero external vector DB — cosine similarity over a Python list is plenty for a
demo (and makes the mechanism totally transparent). In production you'd swap
this list for a real vector store; the interface stays identical.
"""
from __future__ import annotations
import glob
import os

from .llm import embed

KNOWLEDGE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "knowledge")

# Chunk size in words. Kept small so it fits even tiny embedding models like
# all-minilm (~256-token limit). Override with PML_AGENT_CHUNK_WORDS if you use
# a larger embedder (e.g. nomic-embed-text handles 2048+).
CHUNK_WORDS = int(os.environ.get("PML_AGENT_CHUNK_WORDS", "120"))


def _chunk(text, size=None, overlap=20):
    """Split text into overlapping windows so answers don't get cut mid-idea."""
    size = size or CHUNK_WORDS
    words = text.split()
    chunks, i = [], 0
    while i < len(words):
        chunks.append(" ".join(words[i:i + size]))
        i += size - overlap
    return chunks or [""]


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5 or 1.0
    nb = sum(y * y for y in b) ** 0.5 or 1.0
    return dot / (na * nb)


class Knowledge:
    """An in-memory vector index over the knowledge/ folder."""

    def __init__(self):
        self.index = []  # list of {source, text, vector}

    def build(self):
        files = sorted(glob.glob(os.path.join(KNOWLEDGE_DIR, "*.md")) +
                       glob.glob(os.path.join(KNOWLEDGE_DIR, "*.txt")))
        for path in files:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            for chunk in _chunk(content):
                self.index.append({
                    "source": os.path.basename(path),
                    "text": chunk,
                    "vector": embed(chunk),
                })
        return self

    def search(self, question, k=3):
        """Return the top-k most relevant chunks for a question."""
        if not self.index:
            return []
        qv = embed(question)
        scored = [(_cosine(qv, c["vector"]), c) for c in self.index]
        scored.sort(key=lambda s: s[0], reverse=True)
        return [c for _, c in scored[:k]]

    def context_for(self, question, k=3):
        """Format the top hits as a context block to inject into the prompt."""
        hits = self.search(question, k)
        if not hits:
            return ""
        blocks = [f"[{h['source']}]\n{h['text']}" for h in hits]
        return "Relevant knowledge:\n\n" + "\n\n---\n\n".join(blocks)
