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
