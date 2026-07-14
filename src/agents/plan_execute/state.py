
from enum import Enum
from typing import Optional, TypedDict
from pydantic import BaseModel, Field


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


class State(TypedDict):
    input: str
    plan: Optional[Plan]
    output: str