from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator


ArmName = Literal["react", "plan_execute", "plan_execute_synthesis"]
StepType = Literal[
    "plan",
    "tool_call",
    "tool_result",
    "reflection",
    "replan",
    "browser_step",
    "synthesis",
    "interrupt",
]
StepStatus = Literal["running", "success", "failed", "waiting_for_input"]
RunStatus = Literal["running", "success", "failed", "waiting_for_input"]


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
    input: Optional[str] = None
    status: RunStatus
    duration_ms: Optional[int] = None
    started_at: str
    pass_fail: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def resolve_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("input") and data.get("task_name"):
                data["input"] = data["task_name"]
            elif not data.get("task_name") and data.get("input"):
                data["task_name"] = data["input"]
        return data


class RunDetail(BaseModel):
    run_id: str
    arm: ArmName
    task_name: str
    input: Optional[str] = None
    status: RunStatus
    duration_ms: Optional[int] = None
    started_at: str
    ended_at: Optional[str] = None
    pass_fail: Optional[bool] = None
    steps: list[RunStepEvent] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def resolve_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("input") and data.get("task_name"):
                data["input"] = data["task_name"]
            elif not data.get("task_name") and data.get("input"):
                data["task_name"] = data["input"]
        return data


class CreateRunRequest(BaseModel):
    task: str = ""
    input: Optional[str] = None
    arm: ArmName = "plan_execute_synthesis"

    @model_validator(mode="before")
    @classmethod
    def resolve_task_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if not data.get("task") and data.get("input"):
                data["task"] = data["input"]
            elif not data.get("input") and data.get("task"):
                data["input"] = data["task"]
        return data


class ChatMessage(BaseModel):
    run_id: str
    message_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    timestamp: str


class InterruptResponse(BaseModel):
    # Loose envelope to handle different interrupt types
    decision: Optional[Literal["approve", "reject", "alternative"]] = None
    alternative_input: Optional[str] = None
    human_response: Optional[str] = None
    # Note: provided_info omitted since user_info_request not implemented yet


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
