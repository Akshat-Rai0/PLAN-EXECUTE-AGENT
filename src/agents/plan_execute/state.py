
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


def replace_plan(existing: Optional[Plan], new: Optional[Plan]) -> Optional[Plan]:
    """Reducer function to replace the plan with the new value."""
    return new


class State(ExtTypedDict):
    input: str
    plan: Annotated[Optional[Plan], replace_plan]