"""
Programmatic, non-interactive runners for each ablation arm.

The CLI entrypoints (src/agents/plan_execute/main.py,
src/agents/react/main.py) are built for a human at a terminal — they block
on input() for HITL approval and print directly to stdout. For batch eval
across ~20 goals x however-many-arms, we need a version that:
  - never blocks on human input (auto-approves every HITL interrupt)
  - returns a structured result instead of printing
  - captures wall-clock time and operational counters (step count, replan
    count) needed for the ablation's actual metrics
  - fails a single goal without crashing the whole eval run

IMPORTANT — auto-approval and safety:
Auto-approving every HITL gate is safe ONLY because eval runs execute
inside the same sandboxed workspace/subprocess isolation as normal runs
(see src/sandbox/) — auto-approval bypasses the human review step, not the
underlying sandbox boundaries (network allowlist, scratch-dir confinement,
resource caps). It is NOT safe to point this at goals with real
side-effecting intent (e.g. "send an email", "make a payment") — the
golden dataset intentionally contains no such goals. Do not add any.
"""

from __future__ import annotations

import time
import traceback
import uuid
from contextlib import closing
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Optional

import sqlite3

ArmName = Literal["react", "plan_execute_no_synthesis", "plan_execute_full"]


@dataclass
class ArmResult:
    arm: ArmName
    goal_id: str
    goal: str
    success: bool  # did the run complete without crashing (NOT correctness — that's the judge's job)
    final_answer: Optional[str]
    step_count: int
    replan_count: int
    synthesis_count: int
    approval_count: int
    wall_clock_seconds: float
    error: Optional[str] = None
    raw_steps: list[dict] = field(default_factory=list)


def _auto_approve_response(interrupt_payload: dict) -> dict:
    """
    Always approve. Used only for eval batch runs — see module docstring
    for why this is safe in this specific context and not a general
    pattern to reuse elsewhere.
    """
    return {"decision": "approve"}


def run_plan_execute_arm(
    goal_id: str,
    goal: str,
    checkpoint_db_path: str = "eval_checkpoints.db",
    max_wall_clock_seconds: float = 300.0,
    disable_synthesis: bool = False,
) -> ArmResult:
    """
    Run one goal through the Plan-and-Execute agent (LangGraph), auto-
    approving all HITL interrupts, and return a structured result.

    disable_synthesis=False (default) -> Arm 3, "full system": synthesis
        and HITL gates both active, matching what actually ships.
    disable_synthesis=True -> Arm 2, "Plan-and-Execute, no synthesis":
        approximates the spec's Arm 2 by forcing any step that would have
        routed to synthesize_tool to instead be marked FAILED with a clear
        "synthesis disabled for this arm" error, so the replanner reacts
        to it the same way it reacts to any other tool failure.

        IMPORTANT CAVEAT: the actual graph (src/agents/plan_execute/graph.py)
        has synthesis wired unconditionally into _route_to_tool — there is
        no feature flag in the source. This function achieves the
        Arm-2-without-synthesis behavior via a runtime monkey-patch of
        synthesize_tool_node for the duration of this call, which is
        reverted immediately after (in a try/finally) regardless of
        outcome. This is an eval-harness-only mechanism — it does not
        change, and should not be read as changing, the shipped agent's
        real behavior. If the project spec's three-arm structure is worth
        keeping long-term, the cleaner fix is an actual
        ENABLE_SYNTHESIS env var or graph-build parameter in
        graph.py itself — flagging that as a follow-up rather than
        doing it here, since it's a source-code architecture change, not
        an eval-harness concern.
    """
    from src.agents.plan_execute.state import State, StepStatus
    from src.agents.plan_execute.graph import build_graph
    from langgraph.types import Command
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

    start = time.monotonic()
    raw_steps: list[dict] = []

    # Monkey-patch synthesize_tool_node for Arm 2 only, restored in finally.
    #
    # IMPORTANT: graph.py does `from .nodes import synthesize_tool_node`,
    # which binds its OWN local reference to the function at import time.
    # Patching src.agents.plan_execute.nodes.synthesize_tool_node has NO
    # effect on what build_graph() actually registers with the graph,
    # since graph.py already holds a direct reference to the original
    # function object, not a lookup through the nodes module. The patch
    # must target graph.py's own namespace instead.
    _patched_module = None
    _original_synthesize_tool_node = None
    if disable_synthesis:
        import src.agents.plan_execute.graph as _graph_module
        from src.agents.plan_execute.state import StepStatus as _StepStatus

        def _synthesis_disabled_node(state: State) -> dict:
            plan = state["plan"]
            if plan is None:
                return {"plan": plan}
            running_step = next(
                (s for s in plan.subtasks if s.status == _StepStatus.RUNNING), None
            )
            if running_step is not None:
                running_step.status = _StepStatus.FAILED
                running_step.error = (
                    "Tool synthesis is disabled for this evaluation arm "
                    "(Arm 2 — Plan-and-Execute without synthesis). No "
                    f"fixed tool matches tool_hint={running_step.tool_hint!r}."
                )
            return {"plan": plan, "steps_executed": 1}

        _patched_module = _graph_module
        _original_synthesize_tool_node = _graph_module.synthesize_tool_node
        _graph_module.synthesize_tool_node = _synthesis_disabled_node

    try:
        graph = build_graph()
        initial_state: State = {
            "input": goal,
            "plan": None,
            "replan_count": 0,
            "steps_executed": 0,
            "consecutive_identical_replans": 0,
            "last_replan_context": None,
            "workspace_path": None,
            "server_url": None,
            "pending_approval": None,
            "approval_events": [],
            "human_questions": [],
        }

        config = {"configurable": {"thread_id": f"eval-{goal_id}-{uuid.uuid4()}"}}

        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("src.agents.plan_execute.state", "StepStatus"),
                ("src.agents.plan_execute.state", "Plan"),
            ]
        )

        with closing(sqlite3.connect(checkpoint_db_path, check_same_thread=False)) as conn:
            checkpointer = SqliteSaver(conn, serde=serializer)
            compiled = graph.compile(checkpointer=checkpointer)

            result = compiled.invoke(initial_state, config)
            approval_count = 0

            while "__interrupt__" in result:
                if time.monotonic() - start > max_wall_clock_seconds:
                    raise TimeoutError(
                        f"Exceeded {max_wall_clock_seconds}s wall-clock budget "
                        "while still awaiting HITL interrupts — treating as a "
                        "failed run rather than hanging the whole eval batch."
                    )
                approval_count += 1
                response = _auto_approve_response(result["__interrupt__"])
                result = compiled.invoke(Command(resume=response), config)

        elapsed = time.monotonic() - start
        plan = result.get("plan")

        if plan is None:
            return ArmResult(
                arm="plan_execute", goal_id=goal_id, goal=goal, success=False,
                final_answer=None, step_count=0, replan_count=0,
                synthesis_count=0, approval_count=approval_count,
                wall_clock_seconds=elapsed, error="No plan produced.",
            )

        for step in plan.subtasks:
            raw_steps.append({
                "id": step.id,
                "task": step.task,
                "tool_hint": step.tool_hint,
                "status": str(step.status),
                "error": step.error,
            })

        synthesis_count = sum(
            1 for s in plan.subtasks
            if s.tool_hint not in (
                "web_search", "tavily_search", "code_executor", "none",
                "setup_workspace", "shell_command", "write_file",
                "file_editor", "delete_file", "start_server",
            )
        )

        return ArmResult(
            arm="plan_execute_no_synthesis" if disable_synthesis else "plan_execute_full",
            goal_id=goal_id,
            goal=goal,
            success=True,
            final_answer=plan.final_answer,
            step_count=result.get("steps_executed", 0),
            replan_count=result.get("replan_count", 0),
            synthesis_count=synthesis_count,
            approval_count=approval_count,
            wall_clock_seconds=elapsed,
            raw_steps=raw_steps,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        return ArmResult(
            arm="plan_execute_no_synthesis" if disable_synthesis else "plan_execute_full",
            goal_id=goal_id, goal=goal, success=False,
            final_answer=None, step_count=0, replan_count=0,
            synthesis_count=0, approval_count=0, wall_clock_seconds=elapsed,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            raw_steps=raw_steps,
        )

    finally:
        # Always restore the real synthesize_tool_node, even if the try
        # block above raised before reaching its own return — leaving the
        # module monkey-patched would silently corrupt every subsequent
        # Arm 3 (or any other) run in the same process for the rest of
        # the eval batch, which would be a much worse bug than anything
        # this function is trying to measure.
        if _patched_module is not None:
            _patched_module.synthesize_tool_node = _original_synthesize_tool_node


def run_react_arm(
    goal_id: str,
    goal: str,
    max_wall_clock_seconds: float = 300.0,
) -> ArmResult:
    """
    Run one goal through the ReAct agent and return a structured result.

    ReAct has no HITL gates (see src/agents/react/state.py — no
    pending_approval field, no interrupts in its graph), so this is a
    simpler single invoke() with no resume loop needed.
    """
    from src.agents.react.state import ReactState
    from src.agents.react.graph import build_react_graph

    start = time.monotonic()

    try:
        graph = build_react_graph()
        initial_state: ReactState = {
            "goal": goal,
            "history": [],
            "final_answer": None,
            "iterations": 0,
            "workspace_path": None,
        }
        config = {"configurable": {"thread_id": f"eval-react-{goal_id}-{uuid.uuid4()}"}}

        result = graph.invoke(initial_state, config)
        elapsed = time.monotonic() - start

        history = result.get("history", [])
        raw_steps = [
            {
                "thought": turn.thought,
                "action": turn.action,
                "action_input": turn.action_input,
                "observation": turn.observation,
            }
            for turn in history
        ]

        return ArmResult(
            arm="react",
            goal_id=goal_id,
            goal=goal,
            success=True,
            final_answer=result.get("final_answer"),
            step_count=result.get("iterations", len(history)),
            replan_count=0,  # ReAct has no replan concept — always 0, not N/A
            synthesis_count=0,  # ReAct has no tool synthesis
            approval_count=0,  # ReAct has no HITL gates
            wall_clock_seconds=elapsed,
            raw_steps=raw_steps,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        return ArmResult(
            arm="react", goal_id=goal_id, goal=goal, success=False,
            final_answer=None, step_count=0, replan_count=0,
            synthesis_count=0, approval_count=0, wall_clock_seconds=elapsed,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
        )
