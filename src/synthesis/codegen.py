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
from src.agents.prompts.loader import load_prompt

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


def declare_schema(goal: str, step_task: str, context_block: str, llm, registry=None) -> SynthesisSchema:
    """
    First call: ask the LLM to declare the I/O contract for the missing
    capability, BEFORE any code is written. Raises if the LLM's response
    isn't valid JSON matching SynthesisSchema -- callers (synthesize_tool_node)
    are expected to catch this and mark the step FAILED, same as every
    other JSON-parsing LLM call in this codebase (write_file_node,
    delete_file_node, approval_node's pre-generation all follow this
    fail-the-step-not-the-process convention).

    WHEN TO USE (triggered automatically by synthesize_tool_node):
    - When a step's tool_hint doesn't match any fixed tool in the registry
    - When the planner requests a capability not in the standard tool set
    - When reusable functionality is needed across multiple steps
    - When the same computation logic needs to be applied to different inputs
    - For specialized calculations, data transformations, or API integrations

    WHEN NOT TO USE:
    - For one-off calculations (use code_executor instead)
    - When standard tools suffice (search, shell, file operations)
    - For simple operations that don't need reusability
    - When the task can be accomplished with existing fixed tools

    EXAMPLES of synthesized capabilities:
    - "convert_temperature_units" - Converts between Fahrenheit/Celsius/Kelvin
    - "fetch_exchange_rate" - Gets currency exchange rates from an API
    - "calculate_hash" - Computes cryptographic hashes of strings
    - "parse_custom_format" - Parses proprietary data formats
    - "apply_business_logic" - Applies domain-specific calculations

    REUSABILITY PATTERN:
    - First occurrence: Triggers synthesis, creates new tool
    - Subsequent occurrences: Reuses existing tool from registry
    - Same tool_hint string = same tool reuse
    - Different tool_hint = new synthesis even for similar logic

    `registry` (if provided) is consulted so the LLM can recognize when an
    already-synthesized tool covers this step's need and return that EXACT
    capability_name, rather than inventing a fresh, differently-worded name
    every time similar-but-not-identically-phrased steps show up. Without
    this, synthesize_tool_node's reuse-lookup (keyed on capability_name)
    never fires in practice, because declare_schema had no way to know a
    matching capability already existed — see the temperature-conversion
    trace in this module's docstring for the motivating failure.

    Args:
        goal: The overall goal from the user's original request
        step_task: The specific step task that needs this new capability
        context_block: Results from prior steps that provide context
        llm: The LLM instance to use for schema declaration
        registry: Optional tool registry for checking existing capabilities

    Returns:
        SynthesisSchema with capability_name, description, input/output schemas

    Raises:
        json.JSONDecodeError: If LLM response isn't valid JSON
        ValidationError: If JSON doesn't match SynthesisSchema structure
    """
    existing_capabilities_block = "(none synthesized yet this run)"
    if registry is not None:
        existing = registry.list_all()
        if existing:
            lines = []
            for name, tool in existing.items():
                lines.append(
                    f'- "{name}": {tool.description} '
                    f"(input: {tool.input_description}; output: {tool.output_description})"
                )
            existing_capabilities_block = "\n".join(lines)

    prompt = load_prompt("plan_execute_synthesis", "tool_schema").format(**locals())

    response = llm.invoke([
        SystemMessage(content=load_prompt("plan_execute_synthesis", "tool_schema_system")),
        HumanMessage(content=prompt),
    ])
    raw = _strip_markdown_fences(response.content)
    data = json.loads(raw)
    return SynthesisSchema(**data)


def generate_function_code(schema: SynthesisSchema, llm, previous_error: str = None) -> str:
    """
    Second call: generate a single pure Python function against the
    already-declared schema.

    WHEN TO USE (triggered automatically after declare_schema succeeds):
    - When schema declaration was successful and needs implementation
    - When previous code generation failed and needs retry with error feedback
    - When a reusable tool needs to be created from the declared schema
    - After validation fails and the code needs to be fixed

    WHEN NOT TO USE:
    - Before schema declaration (must declare schema first)
    - When the schema declaration failed (fix schema first)
    - For non-Python implementations (Python-only for sandbox safety)
    - When the capability doesn't need a reusable tool

    EXAMPLES of generated code patterns:
    - Temperature conversion: Function taking (value, from_unit, to_unit) dict
    - Hash calculation: Function taking (input_string, algorithm) dict
    - Data transformation: Function taking (data, transformation_type) dict
    - Business logic: Function implementing domain-specific calculations
    - Format parsing: Function taking (raw_data, format_type) dict

    CONSTRAINTS (for security and reusability):
    - No input() calls (non-interactive execution only)
    - No file I/O operations (use write_file_tool for file operations)
    - No network calls (use shell_command_tool or dedicated tools)
    - No external package imports beyond standard library
    - Must print JSON object as last line of stdout
    - Pure computation only (no side effects)

    SECURITY CONSIDERATIONS:
    - Code runs in sandboxed environment with resource limits
    - No filesystem access beyond standard library
    - No network access (prevents unauthorized API calls)
    - Memory and timeout limits prevent resource exhaustion
    - Standard library only (no pip install during execution)

    WORKFLOW:
    1. declare_schema creates the contract (input/output shapes)
    2. generate_function_code creates implementation
    3. validator tests the code in sandbox
    4. If validation fails, retry with error feedback
    5. On success, register tool for reuse across steps

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

    Args:
        schema: The SynthesisSchema from declare_schema with capability contract
        llm: The LLM instance to use for code generation
        previous_error: Optional error message from previous failed generation attempt

    Returns:
        Raw Python code as a string (no markdown fences, ready for sandbox execution)
    """
    retry_note = (
        f"\n\nThe previous attempt failed validation with this error:\n{previous_error}\n"
        f"Fix the code and try again."
        if previous_error
        else ""
    )

    prompt = load_prompt("plan_execute_synthesis", "tool_implementation").format(**locals())    response = llm.invoke([
        SystemMessage(content=load_prompt("plan_execute_synthesis", "tool_implementation_system")),
        HumanMessage(content=prompt),
    ])
    return _strip_markdown_fences(response.content)
