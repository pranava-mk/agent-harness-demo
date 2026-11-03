"""
agent/tools.py — THE TOOL-CALLING PIECE
=======================================

An LLM can only produce text. Tools are how it touches the real world — run a
calculation, query data, take an action. A "tool" here is just:

  • a Python function that does real work, plus
  • a JSON schema describing it (name, what it does, what args it needs)

We hand the schemas to the LLM. When it decides to use one, it replies with a
tool_call (name + arguments). OUR code — not the model — actually runs the
function and hands the result back. The model never executes anything itself.

Add a new capability by writing a function and decorating it with @tool. That's
the whole extension story.
"""
from __future__ import annotations
import json

REGISTRY = {}   # name -> {"fn": callable, "schema": {...}}


def tool(description, params):
    """Decorator: register a function as an LLM-callable tool.

    params: {arg_name: (json_type, description)}
    """
    def wrap(fn):
        properties = {
            name: {"type": typ, "description": desc}
            for name, (typ, desc) in params.items()
        }
        REGISTRY[fn.__name__] = {
            "fn": fn,
            "schema": {
                "type": "function",
                "function": {
                    "name": fn.__name__,
                    "description": description,
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": list(params.keys()),
                    },
                },
            },
        }
        return fn
    return wrap


def schemas():
    """All tool schemas, for handing to the LLM."""
    return [t["schema"] for t in REGISTRY.values()]


def run(name, arguments):
    """Execute a tool by name. Returns a string result (always safe to print)."""
    if name not in REGISTRY:
        return f"Error: no such tool '{name}'"
    try:
        result = REGISTRY[name]["fn"](**arguments)
        return result if isinstance(result, str) else json.dumps(result)
    except Exception as e:  # never let a tool crash the loop
        return f"Error running {name}: {e}"


# ──────────────────────────────────────────────────────────────────────────────
# The actual demo tools. Tiny on purpose — the POINT is the mechanism.
# ──────────────────────────────────────────────────────────────────────────────
@tool("Evaluate a basic arithmetic expression, e.g. '3 * (4 + 1)'.",
      {"expression": ("string", "The arithmetic expression to evaluate")})
def calculate(expression):
    # Locked-down eval: digits and math operators only.
    allowed = set("0123456789+-*/(). %")
    if not set(expression) <= allowed:
        return "Error: only basic arithmetic (digits and + - * / ( ) . %) allowed."
    return str(eval(expression, {"__builtins__": {}}, {}))


@tool("Return today's date and the current time.",
      {})
def current_datetime():
    from datetime import datetime
    return datetime.now().strftime("%A, %d %B %Y, %H:%M")


@tool("Count the words in a piece of text.",
      {"text": ("string", "The text to count words in")})
def word_count(text):
    return f"{len(text.split())} words"
