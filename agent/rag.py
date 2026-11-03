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

# Chunk size in words. Default suits nomic-embed-text (handles ~2048 tokens).
# On a tiny embedder like all-minilm (~256-token limit) drop this to ~120 via
# PML_AGENT_CHUNK_WORDS.
CHUNK_WORDS = int(os.environ.get("PML_AGENT_CHUNK_WORDS", "500"))

# Minimum cosine similarity for a chunk to count as "relevant" and be injected.
# This is what stops RAG from firing on questions the knowledge base can't help
# with (e.g. arithmetic) — below this, we retrieve nothing and let the LLM/tools
# handle it. Tuned for nomic-embed-text; small/weak embedders separate poorly, so
# override with PML_AGENT_MIN_SCORE if your retrieval feels too eager or too shy.
MIN_SCORE = float(os.environ.get("PML_AGENT_MIN_SCORE", "0.45"))

# Max chunks to inject when relevant ones exist.
TOP_K = int(os.environ.get("PML_AGENT_TOP_K", "3"))


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

    def search(self, question, k=None, min_score=None):
        """Return relevant chunks for a question — only those scoring above the
        relevance threshold, so unrelated questions retrieve nothing."""
        if not self.index:
            return []
        k = k or TOP_K
        thresh = MIN_SCORE if min_score is None else min_score
        qv = embed(question)
        scored = [(_cosine(qv, c["vector"]), c) for c in self.index]
        scored.sort(key=lambda s: s[0], reverse=True)
        return [c for score, c in scored[:k] if score >= thresh]

    def context_for(self, question, k=None):
        """Format the relevant hits as a context block to inject into the prompt.
        Returns '' when nothing clears the relevance threshold."""
        hits = self.search(question, k)
        if not hits:
            return ""
        blocks = [f"[{h['source']}]\n{h['text']}" for h in hits]
        return "Relevant knowledge:\n\n" + "\n\n---\n\n".join(blocks)
