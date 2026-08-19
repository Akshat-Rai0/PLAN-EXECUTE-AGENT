"""Planning node and date-anchor helpers."""

import re
from datetime import date

from langchain_core.runnables.config import RunnableConfig

from ..state import State, Step, StepStatus, Plan
from .common import _pkg
from .common import _emit_viz_event, current_run_id, current_arm, _viz_now
from src.api.models import RunStepEvent, StepPayload, utc_now_iso

_YEAR_PATTERN = re.compile(r"\b(19|20)\d{2}\b")


_SHORT_RESULT_CHAR_LIMIT = 200

_RECENCY_KEYWORDS = re.compile(
    r"\b(latest|recent(?:ly)?|current(?:ly)?|now|todays?|this year|this month|"
    r"this week|so far|up[- ]to[- ]date|as of|ongoing|most recent)\b",
    re.IGNORECASE,
)

# Goals that are PURELY asking for the current date/day/time — as opposed to
# goals that merely reference recency in passing while asking about something
# else (e.g. "who won the world cup this year"). For these, planning and
# searching is pure waste: the whole goal is answered by a single
# _pkg().today_date() call. Matched narrowly on purpose — this should only catch
# goals where the date genuinely IS the entire question, not just a
# component of a larger one.
_PURE_DATE_QUERY = re.compile(
    r"^\s*(what'?s?|whats|what is|tell me|give me)?\s*"
    r"(today'?s?|the current|current)\s*(date|day)\s*\??\s*$",
    re.IGNORECASE,
)


def _is_pure_date_query(goal: str) -> bool:
    """Return True if the goal is asking ONLY for today's date/day, with
    nothing else — in which case planning and searching are unnecessary."""
    return bool(_PURE_DATE_QUERY.match(goal.strip()))


def _needs_date_anchor(goal: str) -> bool:
    """Return True if the goal contains recency language that needs today's
    actual date resolved before anything else runs."""
    return bool(_RECENCY_KEYWORDS.search(goal))


def _make_date_anchor_step(next_id: int) -> Step:
    """
    Build a deterministic first step that calls _pkg().today_date() directly —
    no LLM call, no search, just the real system date — and prepend it to
    the plan. Marked DONE immediately since there's nothing to execute; the
    fact is already known.
    """
    return Step(
        id=next_id,
        task="Determine today's actual date to anchor all recency-related reasoning and searches in this plan.",
        tool_hint="none",
        status=StepStatus.DONE,
        result=f"Today's date is {_pkg().today_date()}.",
    )


def plan_node(state: State, config: RunnableConfig | None = None) -> dict:
    """Break down the input task into a plan using the breakdown_task function.

    Two deterministic shortcuts, both bypassing the LLM planner's own
    (inconsistent) judgment about when the date matters:

    1. Pure date queries ("what's today's date?", "whats todays date?") skip
       planning and search entirely — a single DONE step with the real date
       and an immediate final_answer is the whole plan. Previously even this
       trivial case triggered a full web search for something the process
       already knows via _pkg().today_date().

    2. Goals that merely REFERENCE recency ("who won the world cup this
       year") get a date-anchor step prepended before the LLM planner's own
       steps, so every later step/search has the real date available from
       the start — see _extract_search_context, which auto-folds short prior
       results (including this anchor) into later search queries.
    """
    goal = state.get("input", "")

    print(f"\n{'='*80}")
    print(f"📋 Creating Plan")
    print(f"{'='*80}")
    print(f"Goal: {goal}")

    tracker = None
    if config and "configurable" in config and "tracker" in config["configurable"]:
        tracker = config["configurable"]["tracker"]
        from src.api.models import RunStepEvent, StepPayload, utc_now_iso
        tracker.handle_event(
            RunStepEvent(
                run_id=tracker.run_id,
                step_id=f"{tracker.run_id}-plan",
                parent_step_id=None,
                arm=tracker.arm,
                type="plan",
                status="running",
                title="Generating plan…",
                started_at=utc_now_iso(),
                payload=StepPayload(args={"goal": goal}),
            )
        )
    elif _emit_viz_event is not None and current_run_id():
        _emit_viz_event(
            RunStepEvent(
                run_id=current_run_id(),
                step_id=f"{current_run_id()}-plan",
                parent_step_id=None,
                arm=current_arm(),
                type="plan",
                status="running",
                title="Generating plan…",
                started_at=_viz_now(),
                payload=StepPayload(args={"goal": goal}),
            )
        )

    if _is_pure_date_query(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        plan = Plan(
            goal=goal,
            subtasks=[anchor_step],
            final_answer=anchor_step.result,
        )
        print(f"✅ Pure date query - skipping planning")
        return {"plan": plan}

    plan = _pkg().breakdown_task(goal)

    if _needs_date_anchor(goal):
        anchor_step = _make_date_anchor_step(next_id=1)
        # Renumber the planner's own steps to come after the anchor step.
        for i, step in enumerate(plan.subtasks, start=2):
            step.id = i
        plan.subtasks = [anchor_step] + plan.subtasks

    print(f"✅ Plan created with {len(plan.subtasks)} steps:")
    for step in plan.subtasks:
        print(f"   Step {step.id}: {step.task} (tool: {step.tool_hint})")

    return {"plan": plan}
