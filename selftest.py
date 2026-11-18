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

# 2d. PDF extraction: per-font CMap resolution. Two different embedded
# fonts can legitimately reuse the same CID for different characters -- a
# naive "merge every CMap into one table" approach would silently pick
# whichever font's mapping was parsed last (WRONG for one of the two). This
# builds a minimal hand-rolled two-font PDF where /F1's CID 0x0001 means 'A'
# and /F2's CID 0x0001 means 'Z', and checks real per-font disambiguation
# happens (not just "didn't crash").
def _make_multifont_pdf():
    objects = {}
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>"
    objects[3] = (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] "
                  b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> /Contents 4 0 R >>")
    content = b"BT /F1 12 Tf <0001> Tj ET\nBT /F2 12 Tf <0001> Tj ET"
    objects[4] = b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream"
    objects[5] = b"<< /Type /Font /Subtype /Type0 /ToUnicode 7 0 R >>"
    objects[6] = b"<< /Type /Font /Subtype /Type0 /ToUnicode 8 0 R >>"
    cmap1 = b"/CIDInit /ProcSet findresource begin\n1 beginbfchar\n<0001> <0041>\nendbfchar\n"
    cmap2 = b"/CIDInit /ProcSet findresource begin\n1 beginbfchar\n<0001> <005A>\nendbfchar\n"
    objects[7] = b"<< /Length %d >>\nstream\n" % len(cmap1) + cmap1 + b"\nendstream"
    objects[8] = b"<< /Length %d >>\nstream\n" % len(cmap2) + cmap2 + b"\nendstream"
    parts = [b"%PDF-1.4\n"]
    for num, body in sorted(objects.items()):
        parts.append(b"%d 0 obj\n" % num + body + b"\nendobj\n")
    parts.append(b"%%EOF\n")
    return b"".join(parts)

multifont_pdf = _make_multifont_pdf()
merged_only = pdf_extract._build_cid_to_unicode_map(multifont_pdf)
multifont_text = pdf_extract.extract_text(multifont_pdf)
check("merged-only cmap collides on CID 1 (demonstrates the bug per-font fixes)",
      len(merged_only) == 1 and merged_only[1] in ("A", "Z"))
check("per-font resolution disambiguates colliding CIDs correctly",
      "A" in multifont_text and "Z" in multifont_text)

# 3. The loop: plain reply, and a tool-call round-trip.
a = Agent()
ans = a.ask("hello there")
check("loop returns a plain answer", isinstance(ans, str) and len(ans) > 0)

a2 = Agent(use_rag=False)
ans2 = a2.ask("please calculate something")
check("loop drives a tool call + summarises", "tool result" in ans2.lower())

# 3b. The loop: bounded conversation history. A long-running session (e.g.
# the web UI, whose Agent instance lives for the whole server process)
# must not accumulate every message ever sent -- that's unbounded memory
# growth AND a correctness trap (stale RAG/tool context lingering forever).
from agent.loop import MAX_HISTORY_TURNS
a3 = Agent(use_rag=False)
for i in range(MAX_HISTORY_TURNS + 10):
    a3.ask(f"ping number {i}, just calculate 1+1")
user_turns = sum(1 for m in a3.messages if m["role"] == "user")
check(f"conversation history is capped at {MAX_HISTORY_TURNS} turns",
      user_turns == MAX_HISTORY_TURNS)
check("history still starts with the system prompt after trimming",
      a3.messages[0]["role"] == "system")
check("oldest turn's tool call/result wasn't left dangling after trimming",
      not (a3.messages[1]["role"] == "tool"))

print()
if ok:
    print("  ✅ ALL CHECKS PASSED — harness is wired correctly.\n")
    raise SystemExit(0)
print("  ❌ SOME CHECKS FAILED\n")
raise SystemExit(1)
