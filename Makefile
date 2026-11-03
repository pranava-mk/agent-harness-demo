# Agent Harness Demo — handy shortcuts.
.PHONY: chat selftest demo install

chat:            ## Chat with the agent (needs ollama + a pulled model)
	@python3 chat.py

chatv:           ## Chat, verbose (shows retrieval + tool calls)
	@python3 chat.py -v

selftest:        ## Verify the whole harness offline (no model needed)
	@PML_AGENT_BACKEND=stub python3 selftest.py

demo:            ## Run three scripted questions end-to-end (needs a model)
	@python3 examples/demo.py

install:         ## Re-run local setup (venv + deps + models)
	@bash install.sh
