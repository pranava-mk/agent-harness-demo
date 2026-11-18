# Agent Harness Demo — handy shortcuts.
#
# Every target below uses an ABSOLUTE path to this Makefile's own directory
# (ROOT) and to the uv-managed venv's python inside it (PY) — so `make -C
# /abs/path/to/agent-harness-demo web` works correctly from any cwd, with no
# `cd` and no "did I activate the venv?" step.
.PHONY: web chat chatv selftest demo install update

ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
PY   := $(ROOT)/.venv/bin/python3

web:             ## Open the web chat UI (recommended — shows RAG + tools + PDF upload live)
	@$(PY) $(ROOT)/web.py

chat:            ## Chat in the terminal (needs ollama + a pulled model)
	@$(PY) $(ROOT)/chat.py

chatv:           ## Terminal chat, verbose (shows retrieval + tool calls)
	@$(PY) $(ROOT)/chat.py -v

selftest:        ## Verify the whole harness offline (no model needed)
	@PML_AGENT_BACKEND=stub $(PY) $(ROOT)/selftest.py

demo:            ## Run three scripted questions end-to-end (needs a model)
	@$(PY) $(ROOT)/examples/demo.py

install:         ## Re-run setup (self-updates the repo, rebuilds the uv venv + deps + models)
	@bash $(ROOT)/install.sh

update:          ## Same as install — pulls latest + rebuilds the environment
	@bash $(ROOT)/install.sh
