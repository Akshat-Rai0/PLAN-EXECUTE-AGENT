from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


ArmName = Literal["react", "plan_execute", "plan_execute_synthesis"]
StepType = Literal[
    "plan",
    "tool_call",
    "tool_result",
    "reflection",
    "replan",
    "browser_step",
    "synthesis",
]
StepStatus = Literal["running", "success", "failed"]
RunStatus = Literal["running", "success", "failed"]


class TokenUsage(BaseModel):
    input: int = 0
    output: int = 0


class StepPayload(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] | str | None = None
    tool_name: Optional[str] = None
    model: Optional[str] = None
    tokens: TokenUsage = Field(default_factory=TokenUsage)
    error: Optional[str] = None
    screenshot_url: Optional[str] = None


class RunStepEvent(BaseModel):
    run_id: str
    step_id: str
    parent_step_id: Optional[str] = None
    arm: ArmName
    type: StepType
    status: StepStatus
    title: str
    started_at: str
    ended_at: Optional[str] = None
    payload: StepPayload = Field(default_factory=StepPayload)


class RunSummary(BaseModel):
    run_id: str
    arm: ArmName
    task_name: str
    status: RunStatus
    duration_ms: Optional[int] = None
    started_at: str
    pass_fail: Optional[bool] = None


class RunDetail(BaseModel):
    run_id: str
    arm: ArmName
    task_name: str
    status: RunStatus
    duration_ms: Optional[int] = None
    started_at: str
    ended_at: Optional[str] = None
    pass_fail: Optional[bool] = None
    steps: list[RunStepEvent] = Field(default_factory=list)


class CreateRunRequest(BaseModel):
    task: str
    arm: ArmName = "plan_execute_synthesis"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
