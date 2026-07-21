"""
LLM-driven schema declaration and code generation for synthesized tools.

Two LLM calls, matching the two-step "declare, then generate against the
declaration" pattern already used elsewhere in this codebase (e.g.
approval_node pre-generating a command before the interrupt fires, and
code_executor_node's separate args-determination call before its main
code-gen call). Declaring the schema FIRST, as its own call, means the
schema reflects what capability is actually needed -- not a shape reverse
-engineered from whatever code the LLM happened to write.
"""

import json

from langchain_core.messages import HumanMessage, SystemMessage

from .schema import SynthesisSchema


def _strip_markdown_fences(text: str) -> str:
    """Same convention used throughout nodes.py (write_file_node,
    code_executor_node, approval_node's pre-generation, etc.) -- LLMs
    frequently wrap output in ``` fences despite being told not to.
    """
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def declare_schema(goal: str, step_task: str, context_block: str, llm) -> SynthesisSchema:
    """
    First call: ask the LLM to declare the I/O contract for the missing
    capability, BEFORE any code is written. Raises if the LLM's response
    isn't valid JSON matching SynthesisSchema -- callers (synthesize_tool_node)
    are expected to catch this and mark the step FAILED, same as every
    other JSON-parsing LLM call in this codebase (write_file_node,
    delete_file_node, approval_node's pre-generation all follow this
    fail-the-step-not-the-process convention).
    """
    prompt = f"""You are declaring the contract for a new reusable tool needed to complete one step of a task. No existing tool matches this need.

Overall goal: "{goal}"
Step that needs this new capability: {step_task}

Prior steps and results:
{context_block}

Declare a JSON object with exactly these keys:
- "capability_name": a short snake_case identifier, e.g. "convert_temperature_units" or "fetch_exchange_rate"
- "description": one sentence describing what this tool does
- "input_description": plain-English description of the input shape (this tool will be called with a single JSON object as input)
- "output_description": plain-English description of the output shape (this tool must return a single JSON object)
- "example_input": a concrete example input object matching input_description — this will be used to test the generated function

Rules:
- The capability should be genuinely reusable — general enough that a similarly-phrased future step could use it too, not hyper-specific to this exact step's wording.
- Keep the input/output shapes simple: flat JSON objects with string/number/bool/list values, no nested custom types.
- No markdown fences. Output only the raw JSON object."""

    response = llm.invoke([
        SystemMessage(content="You output only a raw JSON object matching the requested schema, no markdown."),
        HumanMessage(content=prompt),
    ])
    raw = _strip_markdown_fences(response.content)
    data = json.loads(raw)
    return SynthesisSchema(**data)


def generate_function_code(schema: SynthesisSchema, llm, previous_error: str = None) -> str:
    """
    Second call: generate a single pure Python function against the
    already-declared schema.

    Constraints deliberately mirror code_executor_node's generation prompt
    (see nodes.py) plus additions specific to a REUSABLE tool rather than a
    one-off step:
      - no input() (same reason as code_executor_node: non-interactive execution)
      - no file I/O, no network — pure computation only. A synthesized tool
        that needs the filesystem or network is a much larger security
        surface to trust for unattended reuse across future steps/runs;
        those needs should go through the existing write_file/shell_command
        tools instead, not through synthesis.
      - must print a single JSON object as the last line of stdout (the
        same convention run_in_sandbox()/SandboxResult already expect)
    """
    retry_note = (
        f"\n\nThe previous attempt failed validation with this error:\n{previous_error}\n"
        f"Fix the code and try again."
        if previous_error
        else ""
    )

    prompt = f"""Write a single Python function implementing this tool:

Capability: {schema.capability_name}
Description: {schema.description}
Input shape: {schema.input_description}
Output shape: {schema.output_description}

Rules:
- Define exactly one function that takes a single dict argument and returns a single dict.
- At the bottom of the script, read the input as JSON from sys.argv[1] (a single command-line
  argument containing the JSON-encoded input object), call your function with the parsed dict,
  and print the result as a single JSON object using print(json.dumps(result)) — this must be
  the LAST line of output. Example bottom-of-script pattern:
      import sys, json
      input_data = json.loads(sys.argv[1])
      result = your_function_name(input_data)
      print(json.dumps(result))
- Pure computation only: no input(), no file I/O, no network calls, no external packages — standard
  library only (json, math, datetime, re, etc. are fine).
- Keep it simple and correct for the declared shape.
- Do not include markdown code fences — output only the raw Python code.{retry_note}"""

    response = llm.invoke([
        SystemMessage(content="You are a Python code generator. Output only raw Python code, no markdown fences, no explanations."),
        HumanMessage(content=prompt),
    ])
    return _strip_markdown_fences(response.content)