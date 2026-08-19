"""Shared helpers for plan-execute graph nodes."""

import os
import re
from datetime import date

from langchain_core.messages import HumanMessage

from ..state import State, Step, StepStatus

try:
    from src.api.observer import emit_event as _emit_viz_event, current_run_id, current_arm
    from src.api.models import RunStepEvent, StepPayload, utc_now_iso as _viz_now
except ImportError:
    _emit_viz_event = None  # type: ignore[assignment,misc]
    current_run_id = lambda: ""  # type: ignore[assignment,misc]
    current_arm = lambda: "plan_execute_synthesis"  # type: ignore[assignment,misc]


def _pkg():
    """Return the nodes package — patch targets live on this namespace."""
    import src.agents.plan_execute.nodes as pkg
    return pkg

def _emit_synthesis_event(step_id: str, title: str, result: dict, status: str = "running") -> None:
    if _emit_viz_event is None:
        return
    _emit_viz_event(
        RunStepEvent(
            run_id=current_run_id(),
            step_id=f"synthesis-{step_id}-{abs(hash(title)) % 100000}",
            parent_step_id=f"step-{step_id}",
            arm=current_arm(),
            type="synthesis",
            status=status,  # type: ignore[arg-type]
            title=title,
            started_at=_viz_now(),
            ended_at=_viz_now() if status != "running" else None,
            payload=StepPayload(result=result),
        )
    )


def _log_approval(state: State, tool: str, details: str) -> dict:
    """
    Log LOW-risk tool execution without interrupting.
    
    This is called before LOW-risk tool execution to provide visibility
    into what the agent is doing without requiring human approval.
    """
    approval_event = {
        "tool": tool,
        "risk_level": "LOW",
        "details": details,
        "timestamp": date.today().isoformat(),
    }
    print(f"⚠️ Executing LOW-risk operation: {tool} - {details[:100]}")
    return {"approval_events": [approval_event]}


def _verify_step_result(step: Step) -> tuple[bool, str, str]:
    """
    Returns (is_verified, missing_entities_hint, error_message).
    If success_criterion is None, always returns True.
    """
    if not step.success_criterion:
        return True, "", ""

    result_text = step.result or ""
    
    # Cheap check: if criterion mentions numbers/quantities, ensure digits exist
    quantity_keywords = {"number", "seconds", "margin", "gap", "points", "score", "count", "amount", "date", "time", "price"}
    needs_quantity = any(k in step.success_criterion.lower() for k in quantity_keywords)
    if needs_quantity and not re.search(r'\d', result_text):
        return False, "", "Result missing numeric data required by success criterion."

    prompt = (
        f"Does the following text contain this specific information: {step.success_criterion}?\n\n"
        f"Text: {result_text}\n\n"
        "Answer ONLY with YES or NO on the first line.\n"
        "If NO, on the second line, list 1-3 key entities (names, places, etc.) present in the text to help refine the search."
    )
    
    cheap_llm = _pkg().get_cheap_llm()
    try:
        response = cheap_llm.invoke([HumanMessage(content=prompt)])
        content = response.content.strip().split('\n')
        is_yes = content[0].strip().upper().startswith("YES")
        hint = content[1].strip() if len(content) > 1 and not is_yes else ""
        if not is_yes:
            return False, hint, f"Failed verification for criterion: {step.success_criterion}"
        return True, "", ""
    except Exception as e:
        # Fallback to True if verification LLM fails to avoid blocking the pipeline
        print(f"⚠️ Verification check failed: {e}")
        return True, "", ""


def _build_coding_context(plan, current_step) -> str:
    """Build a short prior-steps context block for coding node prompts."""
    prior = []
    for step in plan.subtasks:
        if step.id >= current_step.id:
            break
        if step.status == StepStatus.DONE and step.result:
            text = step.result if len(step.result) <= 1200 else step.result[:1200] + "... [truncated]"
            prior.append(f"Step {step.id} ({step.tool_hint}): {step.task}\nResult: {text}")
    return "\n\n".join(prior) if prior else "(no prior step results)"
