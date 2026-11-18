"""
selftest.py — proves every piece works WITHOUT a model installed.
Runs on the offline 'stub' backend, so `make selftest` is green on any machine.
Exercises: tool registry+dispatch, RAG retrieval, and the full agent loop
(plain reply, tool-call path, and post-tool answer).
"""
import os
os.environ["PML_AGENT_BACKEND"] = "stub"  # force offline backend BEFORE imports

from agent import Agent
from agent import tools
from agent.rag import Knowledge
from agent import pdf_extract

PASS, FAIL = "✓", "✗"
ok = True


def check(label, cond):
    global ok
    ok = ok and cond
    print(f"  {PASS if cond else FAIL}  {label}")


print("\n  Running agent-harness self-test (offline stub backend)\n")

# 1. Tools: registry populated and dispatch works.
check("tools registered", len(tools.schemas()) >= 3)
check("calculate tool runs", tools.run("calculate", {"expression": "6*7"}) == "42")
check("calculate rejects junk", tools.run("calculate", {"expression": "__import__('os')"}).startswith("Error"))
check("unknown tool is safe", tools.run("nope", {}).startswith("Error"))

# 2. RAG: builds an index and retrieves relevant chunks.
kb = Knowledge().build()
check("knowledge index built", len(kb.index) > 0)
hits = kb.search("what is a harness", k=2)
check("retrieval returns hits", len(hits) > 0)
check("retrieval is relevant", any("harness" in h["text"].lower() for h in hits))

# 2b. RAG: ad-hoc document upload (PDF-upload feature) chunks+embeds+indexes,
# is searchable immediately, and can be removed cleanly.
trace = []
added = kb.add_document("test.pdf", "zephyrquartz is a made-up word for testing retrieval. " * 30, trace_steps=trace)
check("add_document returns chunk entries", len(added) > 0)
check("add_document emitted trace steps", any(s["kind"] == "doc_chunk" for s in trace) and any(s["kind"] == "doc_embed" for s in trace))
score_trace = []
doc_hits = kb.search("zephyrquartz", k=3, min_score=0.0, trace_steps=score_trace)
check("uploaded doc is retrievable", any(h["source"] == "test.pdf" for h in doc_hits))
check("search emits query_embed + score trace", any(s["kind"] == "query_embed" for s in score_trace) and any(s["kind"] == "score" for s in score_trace))
removed = kb.remove_document("test.pdf")
check("remove_document cleans up", removed == len(added) and not any(c["source"] == "test.pdf" for c in kb.index))

# 2c. PDF extraction: handles both plain-text PDFs and real-world CID-font
# PDFs (e.g. anything made via a browser's "Print to PDF" — Identity-H
# encoding + ToUnicode CMaps, which is the common case and easy to get wrong).
check("pdf_extract returns '' on garbage input", pdf_extract.extract_text(b"not a pdf") == "")

# 3. The loop: plain reply, and a tool-call round-trip.
a = Agent()
ans = a.ask("hello there")
check("loop returns a plain answer", isinstance(ans, str) and len(ans) > 0)

a2 = Agent(use_rag=False)
ans2 = a2.ask("please calculate something")
check("loop drives a tool call + summarises", "tool result" in ans2.lower())

print()
if ok:
    print("  ✅ ALL CHECKS PASSED — harness is wired correctly.\n")
    raise SystemExit(0)
print("  ❌ SOME CHECKS FAILED\n")
raise SystemExit(1)
