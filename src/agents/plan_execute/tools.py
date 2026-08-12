import json
from pydantic import ValidationError
from langchain_core.messages import HumanMessage, SystemMessage

from .llm import get_llm
from .state import Plan
from src.agents.prompts.loader import load_prompt

MAX_RETRIES = 2
MAX_REPLAN_CONTEXT_CHARS = 12_000
MAX_REPLAN_CONTEXT_ITEM_CHARS = 1_800

PROMPT_TEMPLATE = load_prompt("plan_execute", "planner")

RETRY_SUFFIX = load_prompt("plan_execute", "planner_retry")


def _truncate_context_item(value: str, limit: int = MAX_REPLAN_CONTEXT_ITEM_CHARS) -> str:
    """Keep both the conclusion and tail of a long tool result."""
    if limit <= 0:
        return ""
    if len(value) <= limit:
        return value
    if limit < 80:
        return value[:limit]
    tail_size = min(300, limit // 4)
    head_size = limit - tail_size
    omitted = len(value) - limit
    return f"{value[:head_size]}\n... [{omitted} characters omitted] ...\n{value[-tail_size:]}"


def bound_replan_context(
    context: list[str],
    max_chars: int = MAX_REPLAN_CONTEXT_CHARS,
) -> list[str]:
    """Bound replan input so repeated tool output cannot grow prompts forever.

    The plan and its full results remain available for final synthesis.  This
    only compacts the *working* context sent to the planner/novelty checker.
    """
    bounded: list[str] = []
    used = 0
    for item in context:
        compact = _truncate_context_item(item)
        separator_size = 1 if bounded else 0
        remaining = max_chars - used - separator_size
        if remaining <= 0:
            break
        if len(compact) > remaining:
            compact = _truncate_context_item(compact, remaining)
        bounded.append(compact)
        used += len(compact) + separator_size

    if len(bounded) < len(context):
        marker = f"[Replan context truncated: retained {len(bounded)} of {len(context)} step records]"
        if used + len(marker) + 1 <= max_chars:
            bounded.append(marker)
    return bounded


def _strip_markdown_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        lines = content.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()
    return content


REPLAN_INSTRUCTIONS = load_prompt("plan_execute", "replan_failure")


SUCCESS_REPLAN_INSTRUCTIONS = load_prompt("plan_execute", "replan_success")


def breakdown_task(goal: str, context: list[str] = None, replan_reason: str = "failure") -> Plan:
    """
    Break down a goal into a validated Plan of Steps.
    Retries up to MAX_RETRIES times if the model returns invalid JSON
    or JSON that doesn't satisfy the Plan/Step schema.

    Args:
        goal: The overall goal to plan for.
        context: Optional list of completed/failed step result strings to guide
            replanning. If None, a fresh plan is generated from scratch.
        replan_reason: "failure" (default) uses REPLAN_INSTRUCTIONS focused on
            error recovery; "success_new_info" uses SUCCESS_REPLAN_INSTRUCTIONS
            focused on optimizing remaining steps with newly discovered info.

    Raises RuntimeError if no valid plan is produced after all retries —
    callers must handle this rather than receiving silently broken data.
    """
    llm = get_llm()
    if context:
        # Defence in depth: callers besides replaner can use this public
        # function, so never trust them to have already bounded the context.
        context = bound_replan_context(context)
        context_str = "\n".join(context)
        instructions = (
            SUCCESS_REPLAN_INSTRUCTIONS
            if replan_reason == "success_new_info"
            else REPLAN_INSTRUCTIONS
        )
        prompt = PROMPT_TEMPLATE.format(goal=goal) + instructions.format(context_str=context_str)
    else:
        prompt = PROMPT_TEMPLATE.format(goal=goal)
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        messages = [
            SystemMessage(content=load_prompt("plan_execute", "planner_system")),
            HumanMessage(content=prompt),
        ]
        response = llm.invoke(messages)
        content = _strip_markdown_fences(response.content)

        try:
            data = json.loads(content)
            plan = Plan.model_validate(data)
            return plan
        except (json.JSONDecodeError, ValidationError) as e:
            last_error = e
            if context:
                prompt = PROMPT_TEMPLATE.format(goal=goal) + instructions.format(context_str=context_str) + RETRY_SUFFIX.format(error=str(e))
            else:
                prompt = PROMPT_TEMPLATE.format(goal=goal) + RETRY_SUFFIX.format(error=str(e))
            continue

    raise RuntimeError(
        f"breakdown_task: failed to produce a valid Plan after {MAX_RETRIES + 1} attempts. "
        f"Last error: {last_error}"
    )
