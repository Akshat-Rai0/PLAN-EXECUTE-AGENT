
from enum import Enum
from typing import Optional, TypedDict, Annotated
from pydantic import BaseModel, Field
from typing_extensions import TypedDict as ExtTypedDict
from operator import add


class StepStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"


class Step(BaseModel):
    id: int
    task: str
    tool_hint: str = "none"
    status: StepStatus = StepStatus.PENDING
    sensitive: bool = False
    result: Optional[str] = None
    error: Optional[str] = None


class Plan(BaseModel):
    goal: str
    subtasks: list[Step] = Field(min_length=1)
    final_answer: Optional[str] = None


def replace_plan(existing: Optional[Plan], new: Optional[Plan]) -> Optional[Plan]:
    """Reducer function to replace the plan with the new value."""
    return new


def sum_replan_count(existing: Optional[int], new: Optional[int]) -> int:
    """Reducer function to accumulate replan_count across graph steps."""
    return (existing or 0) + (new or 0)


def sum_steps_executed(existing: Optional[int], new: Optional[int]) -> int:
    """Reducer function to accumulate total executed steps across the run."""
    return (existing or 0) + (new or 0)


class State(ExtTypedDict):
    input: str
    plan: Annotated[Optional[Plan], replace_plan]
    replan_count: Annotated[int, sum_replan_count]
    steps_executed: Annotated[int, sum_steps_executed]