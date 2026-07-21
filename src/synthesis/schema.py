"""
Schema declaration for synthesized tools.

A synthesized tool is only trusted enough to register for reuse if its
generated function's output can be mechanically checked against a declared
shape -- "looks plausible" isn't good enough for something that gets reused
across steps and runs. This mirrors the same convention run_in_sandbox()
already uses for code_executor_node (JSON-on-last-line + output_schema
validation), just applied one layer up: here we're validating a *tool
definition* before it's trusted, not a single step's one-off output.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class SynthesisSchema(BaseModel):
    """
    The LLM-declared contract for a to-be-synthesized tool, produced before
    any code is generated (see codegen.py). Declaring this first -- rather
    than generating code and hoping it's reusable -- is what makes the
    resulting tool's output checkable and its registry key meaningful.
    """

    capability_name: str = Field(
        description=(
            "A short, descriptive, machine-usable identifier for this "
            "capability, e.g. 'convert_temperature_units' or "
            "'fetch_exchange_rate'. Used as the registry key so later steps "
            "needing the same capability can find and reuse this tool "
            "instead of re-synthesizing. snake_case, no spaces."
        )
    )
    description: str = Field(
        description="One sentence describing what this tool does, for a human reviewing it at approval time."
    )
    input_description: str = Field(
        description=(
            "Plain-English description of the input shape, e.g. "
            "'a JSON object with one key: temps_fahrenheit, a list of floats'."
        )
    )
    output_description: str = Field(
        description=(
            "Plain-English description of the output shape, e.g. "
            "'a JSON object with celsius_values (list of floats) and "
            "above_freezing (list of booleans), same length and order as the input'."
        )
    )
    example_input: dict = Field(
        description="A concrete example input matching input_description, used as the validation test case in the sandbox."
    )


class SynthesizedTool(BaseModel):
    """
    A validated, registered synthesized tool -- the runtime registry's
    unit of storage (see registry.py). Only ever constructed after a
    generated function has PASSED sandbox validation; there is no
    "unvalidated tool" state that gets persisted.
    """

    capability_name: str
    description: str
    input_description: str
    output_description: str
    source_code: str = Field(description="The exact validated Python function source.")
    example_input: dict
    example_output: dict = Field(description="The validated output produced by example_input, kept for the approval-time display and for regression checks if the tool is ever re-validated.")
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    times_used: int = 0

    def as_approval_summary(self) -> str:
        """Human-readable summary for the HITL approval prompt (main.py)."""
        return (
            f"Synthesized tool: {self.capability_name}\n"
            f"  {self.description}\n\n"
            f"Source:\n{self.source_code}\n\n"
            f"Validated with example input: {self.example_input}\n"
            f"Produced: {self.example_output}"
        )