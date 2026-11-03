# Agent & Harness Terminology

## What is an LLM?
A Large Language Model is a next-token predictor trained on huge text corpora.
By itself it only turns text in into text out. It has no memory between calls,
no access to your files, and no ability to take actions. Everything it reacts to
must be placed into its input (its "context") on each call.

## What is the context window?
The context window is the maximum amount of text (measured in tokens, roughly
3/4 of a word each) the model can read at once. It holds the system prompt, the
conversation history, any retrieved knowledge, and tool results. It is finite,
so a core engineering job is deciding WHAT to put in it each turn. Stuffing in
too much, or the wrong thing, actually degrades the model's answers.

## What is an agent?
An agent is an LLM placed inside a loop that lets it take actions and observe
results, repeating until a task is done. A chatbot answers once; an agent can
call a tool, read the result, decide what to do next, and only then answer. The
intelligence isn't a new kind of model — it's the loop plus good context.

## What is the agent loop?
observe -> think -> act -> repeat.
  observe: gather the context relevant right now (the question, retrieved docs)
  think:   the LLM decides: answer directly, or call a tool
  act:     if a tool was chosen, YOUR code runs it and feeds the result back
  repeat:  the result re-enters the context and the loop runs again, until the
           LLM responds in plain text with no further tool calls.

## What is a tool (tool calling / function calling)?
A tool is a function the LLM can ask to run. You describe each tool to the model
with a name, a description, and its arguments (a JSON schema). When the model
wants one, it returns a structured tool call (name + arguments). Your harness —
not the model — executes the function and returns the result into the context.
The model never runs code itself; it only requests calls.

## What is a harness?
The harness is the scaffolding code around the LLM: it manages the conversation
state, injects the right context, hands the model its available tools,
intercepts tool-call requests, runs them, and feeds results back — running the
whole loop until the task is done. "Agent harness" = this orchestration layer.
Frameworks (LangGraph, the OpenAI Agents SDK) are harnesses; so is a hand-rolled
loop like the one in this repo.

## What is RAG (knowledge retrieval)?
Retrieval-Augmented Generation gives the model knowledge it wasn't trained on
WITHOUT retraining. You split your documents into chunks, convert each to a
vector embedding (numbers capturing meaning), and store them. At question time
you embed the question, find the most similar chunks, and paste them into the
context before the model answers. This is how an agent "knows" your private docs.

## What is an embedding / vector search?
An embedding is a list of numbers representing the meaning of a piece of text.
Similar meanings produce vectors that point in similar directions, so you can
find relevant text by comparing vectors (cosine similarity) instead of matching
keywords. A vector database stores these at scale; for a small demo a plain list
in memory works identically.

## What is MCP (Model Context Protocol)?
MCP is an open standard for connecting agents to external tools and data through
a uniform interface. Instead of hand-wiring every integration, a tool/data
source runs an "MCP server" exposing its capabilities, and any MCP-aware agent
(the "client") can discover and call them. Think of it as a universal adapter
for agent tools — write a capability once as an MCP server, and any compatible
agent can use it.

## What are skills, and how are they loaded?
A skill is a packaged, reusable capability or procedure an agent can load on
demand — typically a folder with instructions plus optional scripts and
references. Rather than cramming every instruction into the system prompt (and
burning context), the agent loads a skill only when the task matches it. Loading
means pulling that skill's instructions/resources into the context at the moment
they're relevant, then acting on them. This keeps the base context small and the
agent focused, while still giving it deep, specialised know-how when needed.
