# Prompt templates

Prompt templates live in `src/agents/prompts/<arm>/`. Each node-level LLM
instruction has its own Markdown file, named for the node and purpose that
consumes it. The files are deliberately plain text: Markdown is only the file
extension and does not add rendering or processing behavior.

Templates use Python `str.format(...)` at the existing call site. Placeholders
such as `{goal}`, `{context_block}`, and `{error}` remain in the files and are
filled with the same values as before extraction. Literal braces intended for
the model are written as `{{` and `}}`, following Python format-string rules.
The loader removes the single final newline supplied by text files so the
runtime prompt content exactly matches the former inline literals.

| Graph / implementation | Prompt directory |
| --- | --- |
| `src/agents/react/graph.py` and `nodes.py` | `react/` |
| `src/agents/plan_execute/graph.py`, `nodes.py`, and `tools.py` | `plan_execute/` |
| Dynamic tool synthesis used by the Plan-and-Execute synthesis arm (`src/synthesis/codegen.py`) | `plan_execute_synthesis/` |
