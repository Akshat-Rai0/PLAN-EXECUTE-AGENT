
from enum import Enum
from typing import Optional, TypedDict, Annotated
from pydantic import BaseModel, Field
from typing_extensions import TypedDict as ExtTypedDict
from operator import add

from src.tools.risk_classifier import RiskLevel



class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Step(BaseModel):
    id: int
    task: str
    tool_hint: str = "none"
    status: StepStatus = StepStatus.PENDING
    sensitive: bool = False
    result: Optional[str] = None
    error: Optional[str] = None
    approval_required: bool = False  # Whether this step requires human approval


class Plan(BaseModel):
    goal: str
    subtasks: list[Step] = Field(min_length=1)
    final_answer: Optional[str] = None
    cancelled_steps: list[Step] = Field(default_factory=list)


def replace_plan(existing: Optional[Plan], new: Optional[Plan]) -> Optional[Plan]:
    """Reducer function to replace the plan with the new value."""
    return new


def sum_replan_count(existing: Optional[int], new: Optional[int]) -> int:
    """Reducer function to accumulate replan_count across graph steps."""
    return (existing or 0) + (new or 0)


def sum_steps_executed(existing: Optional[int], new: Optional[int]) -> int:
    """Reducer function to accumulate total executed steps across the run."""
    return (existing or 0) + (new or 0)


def replace_last_replan_context(existing: Optional[list], new: Optional[list]) -> Optional[list]:
    """
    Reducer function to replace the stored 'last replan context' with the new
    value. This holds the completed-step results from the most recent replan
    cycle's EXECUTION (i.e. after its new steps actually ran), so the next
    novelty check compares real outcomes against real outcomes instead of
    comparing "results so far" against a freshly-generated, not-yet-executed
    plan (which is always empty and made the novelty check always fail).
    """
    return new if new is not None else existing


def replace_consecutive_identical_replans(existing: Optional[int], new: Optional[int]) -> int:
    """
    Reducer function that REPLACES (not accumulates) consecutive_identical_replans.

    This value needs to reset to 0 when a replan finds new info, and jump to
    an explicit count when it doesn't — replaner always knows the exact value
    it wants this to become, so accumulation (sum_replan_count's behavior) is
    wrong here. Reusing the additive reducer meant returning 0 to "reset" the
    counter actually left it unchanged (added 0 to whatever it already was),
    so it could only ever climb, never reset — masking genuinely fresh
    replans as consecutive-identical ones.
    """
    return new if new is not None else (existing or 0)


def replace_workspace_path(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    """Reducer: replace workspace_path with new value, or keep existing if new is None."""
    return new if new is not None else existing


def replace_server_url(existing: Optional[str], new: Optional[str]) -> Optional[str]:
    """Reducer: replace server_url with new value, or keep existing if new is None."""
    return new if new is not None else existing


def replace_pending_approval(existing: Optional[dict], new: Optional[dict]) -> Optional[dict]:
    """Reducer: replace pending_approval with new value, or keep existing if new is None."""
    return new if new is not None else existing


def add_approval_event(existing: list[dict], new: list[dict]) -> list[dict]:
    """Reducer: append approval events to the list."""
    return existing + new


def add_human_question(existing: list[dict], new: list[dict]) -> list[dict]:
    """Reducer: append human questions to the list."""
    return existing + new


class State(ExtTypedDict):
    input: str
    plan: Annotated[Optional[Plan], replace_plan]
    replan_count: Annotated[int, sum_replan_count]
    steps_executed: Annotated[int, sum_steps_executed]
    consecutive_identical_replans: Annotated[int, replace_consecutive_identical_replans]
    last_replan_context: Annotated[Optional[list], replace_last_replan_context]
    # Coding-agent workspace — set once by setup_workspace_node, threaded
    # through state so every subsequent node knows the project root.
    workspace_path: Annotated[Optional[str], replace_workspace_path]
    # URL of a running dev server, set by start_server_node.
    server_url: Annotated[Optional[str], replace_server_url]
    # HITL fields
    pending_approval: Annotated[Optional[dict], replace_pending_approval]
    approval_events: Annotated[list[dict], add_approval_event]
    human_questions: Annotated[list[dict], add_human_question]