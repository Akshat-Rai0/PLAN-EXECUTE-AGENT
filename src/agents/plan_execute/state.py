from typing import Optional, TypedDict


class State(TypedDict):
    """State with input, plan, and output."""

    input: str
    plan: Optional[str]
    output: str