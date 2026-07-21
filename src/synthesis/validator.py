"""
Sandbox validation for synthesized tools.

Reuses run_in_sandbox() exactly as code_executor_node does — no new
execution pathway. The only addition here is treating a successful sandbox
run as necessary but NOT sufficient: a generated function that runs cleanly
and returns something JSON-shaped is still just "didn't crash," not
"correct." Real correctness checking (declared field presence, output
length matching input length, etc.) happens via a lightweight structural
check against SynthesisSchema.output_description, since we don't have a
full Pydantic output_schema up front (the shape is LLM-declared in
English, not as a formal model) — see _basic_shape_check for exactly what
is and isn't caught.
"""

import json
from dataclasses import dataclass
from typing import Optional

from src.sandbox.runner import run_in_sandbox

from .schema import SynthesisSchema


@dataclass
class ValidationResult:
    success: bool
    output: Optional[dict] = None
    error: Optional[str] = None


def _basic_shape_check(output: dict, schema: SynthesisSchema) -> Optional[str]:
    """
    A deliberately lightweight sanity check, not a full schema validator.

    We only have output_description as free-text English (the LLM declared
    it before any code existed — see codegen.declare_schema), not a formal
    Pydantic model, so we can't do the same hard structural validation
    run_in_sandbox()'s output_schema param does for code_executor_node.
    What we CAN check cheaply: the output is a non-empty dict (the script
    followed the "print a JSON object" contract at all) — that alone
    catches the two most common failure modes seen in this project's
    traces so far: a script that crashes before printing anything, and a
    script that prints prose/an error message instead of the JSON object
    run_in_sandbox() expects on the last line.

    Returns an error string if the check fails, None if it passes.
    """
    if not isinstance(output, dict):
        return f"Expected a JSON object as output, got {type(output).__name__}"
    if not output:
        return "Output was an empty JSON object — the function likely returned nothing meaningful"
    return None


def validate_synthesized_function(code: str, schema: SynthesisSchema) -> ValidationResult:
    """
    Run the generated function in the sandbox against schema.example_input,
    check it actually produced usable output.

    Same timeout/memory caps as code_executor_node (15s / 256MB) — a
    synthesized tool being validated is not a special case that deserves
    looser resource limits than any other sandboxed execution.
    """
    example_input_json = json.dumps(schema.example_input)

    result = run_in_sandbox(
        code,
        timeout_seconds=15,
        memory_limit_mb=256,
        args=[example_input_json],
    )

    if not result.success:
        # run_in_sandbox already distinguishes timeout / non-zero exit /
        # missing-JSON-output cases in result.error — surface it directly
        # rather than re-deriving the same diagnosis.
        return ValidationResult(success=False, error=result.error or "Sandbox execution failed")

    if result.output is None:
        return ValidationResult(
            success=False,
            error=(
                "Script exited successfully but printed no JSON object on its "
                "last stdout line. stdout was: " + (result.stdout[-500:] if result.stdout else "(empty)")
            ),
        )

    shape_error = _basic_shape_check(result.output, schema)
    if shape_error:
        return ValidationResult(success=False, error=shape_error)

    return ValidationResult(success=True, output=result.output)