from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .event_bus import event_bus
from .models import ArmName, RunStepEvent, StepPayload, TokenUsage, utc_now_iso
from .observer import set_emitter, reset_emitter, set_run_context, reset_run_context
from .store import RunStore


def _map_arm_for_eval(arm: str) -> ArmName:
    if arm == "react":
        return "react"
    if arm in ("plan_execute_no_synthesis", "plan_execute"):
        return "plan_execute"
    return "plan_execute_synthesis"


def _step_type_for_tool(tool_hint: str) -> str:
    hint = (tool_hint or "").lower()
    if hint in ("browser_use", "browser-use"):
        return "browser_step"
    if hint == "none":
        return "reflection"
    if hint == "synthesize_tool":
        return "synthesis"
    return "tool_call"


def _parse_browser_model(result: str | None) -> Optional[str]:
    if not result:
        return None
    match = re.search(r"\[browser_use model=([^;\]]+)", result)
    return match.group(1).strip() if match else None


class RunTracker:
    """Tracks in-flight step events while a graph executes."""

    def __init__(self, run_id: str, arm: ArmName, store: RunStore) -> None:
        self.run_id = run_id
        self.arm = arm
        self.store = store
        self._open_steps: dict[str, RunStepEvent] = {}
        self._last_replan_count = 0
        self._last_replan_step_id: Optional[str] = None
        self._plan_emitted = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def _emit(self, event: RunStepEvent) -> None:
        self.store.upsert_step(event)
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(event_bus.publish(event), self._loop)

    def handle_event(self, event: RunStepEvent) -> None:
        self._open_steps[event.step_id] = event
        self._emit(event)

    def update_from_state(self, state: dict[str, Any], node_name: str) -> None:
        plan = state.get("plan")
        if plan is None:
            return

        goal = getattr(plan, "goal", None) or (plan.get("goal") if isinstance(plan, dict) else "")
        subtasks = getattr(plan, "subtasks", None) or (plan.get("subtasks") if isinstance(plan, dict) else [])

        if not self._plan_emitted and subtasks:
            self._plan_emitted = True
            step_ids = []
            for s in subtasks:
                sid = getattr(s, "id", s.get("id") if isinstance(s, dict) else None)
                step_ids.append(str(sid))
            self.handle_event(
                RunStepEvent(
                    run_id=self.run_id,
                    step_id=f"{self.run_id}-plan",
                    parent_step_id=None,
                    arm=self.arm,
                    type="plan",
                    status="success",
                    title=f"Plan: {len(subtasks)} steps",
                    started_at=utc_now_iso(),
                    ended_at=utc_now_iso(),
                    payload=StepPayload(
                        result={
                            "goal": goal,
                            "steps": [
                                {
                                    "id": getattr(s, "id", s.get("id")),
                                    "task": getattr(s, "task", s.get("task")),
                                    "tool_hint": getattr(s, "tool_hint", s.get("tool_hint")),
                                }
                                for s in subtasks
                            ],
                        }
                    ),
                )
            )

        replan_count = state.get("replan_count", 0)
        if replan_count > self._last_replan_count:
            self._last_replan_count = replan_count
            replan_id = f"{self.run_id}-replan-{replan_count}"
            self._last_replan_step_id = replan_id
            self.handle_event(
                RunStepEvent(
                    run_id=self.run_id,
                    step_id=replan_id,
                    parent_step_id=self._last_replan_step_id,
                    arm=self.arm,
                    type="replan",
                    status="success",
                    title=f"Replan #{replan_count}",
                    started_at=utc_now_iso(),
                    ended_at=utc_now_iso(),
                    payload=StepPayload(result={"replan_count": replan_count, "node": node_name}),
                )
            )

        for step in subtasks:
            step_id = str(getattr(step, "id", step.get("id") if isinstance(step, dict) else "?"))
            task = getattr(step, "task", step.get("task") if isinstance(step, dict) else "")
            tool_hint = getattr(step, "tool_hint", step.get("tool_hint") if isinstance(step, dict) else "")
            status = getattr(step, "status", step.get("status") if isinstance(step, dict) else "")
            result = getattr(step, "result", step.get("result") if isinstance(step, dict) else None)
            error = getattr(step, "error", step.get("error") if isinstance(step, dict) else None)

            status_str = str(status).split(".")[-1] if status else ""
            event_key = f"{self.run_id}-step-{step_id}"

            if status_str == "RUNNING" and event_key not in self._open_steps:
                step_type = _step_type_for_tool(tool_hint)
                parent = self._last_replan_step_id if replan_count > 0 else None
                evt = RunStepEvent(
                    run_id=self.run_id,
                    step_id=event_key,
                    parent_step_id=parent,
                    arm=self.arm,
                    type=step_type,  # type: ignore[arg-type]
                    status="running",
                    title=f"{tool_hint}: {task[:80]}",
                    started_at=utc_now_iso(),
                    payload=StepPayload(
                        args={"task": task, "tool_hint": tool_hint, "node": node_name},
                        tool_name=tool_hint,
                    ),
                )
                self.handle_event(evt)

            elif status_str in ("DONE", "FAILED") and event_key in self._open_steps:
                open_evt = self._open_steps[event_key]
                if open_evt.status == "running":
                    open_evt.status = "success" if status_str == "DONE" else "failed"
                    open_evt.ended_at = utc_now_iso()
                    open_evt.payload.result = result
                    open_evt.payload.error = error
                    if tool_hint in ("browser_use", "browser-use"):
                        open_evt.type = "browser_step"
                        open_evt.payload.model = _parse_browser_model(result)
                    self._emit(open_evt)

            elif status_str in ("DONE", "FAILED") and event_key not in self._open_steps:
                step_type = _step_type_for_tool(tool_hint)
                evt = RunStepEvent(
                    run_id=self.run_id,
                    step_id=event_key,
                    parent_step_id=self._last_replan_step_id,
                    arm=self.arm,
                    type=step_type,  # type: ignore[arg-type]
                    status="success" if status_str == "DONE" else "failed",
                    title=f"{tool_hint}: {task[:80]}",
                    started_at=utc_now_iso(),
                    ended_at=utc_now_iso(),
                    payload=StepPayload(
                        args={"task": task, "tool_hint": tool_hint},
                        result=result,
                        error=error,
                        tool_name=tool_hint,
                        model=_parse_browser_model(result) if step_type == "browser_step" else None,
                    ),
                )
                self.handle_event(evt)


def seed_from_agent_outputs(store: RunStore, repo_root: Path) -> int:
    """Import finished runs from agent_outputs/ for replay."""
    outputs_dir = repo_root / "agent_outputs"
    if not outputs_dir.exists():
        return 0

    imported = 0
    for run_dir in sorted(outputs_dir.iterdir()):
        if not run_dir.is_dir():
            continue
        plan_path = run_dir / "plan.json"
        react_path = run_dir / "react-trace.json"
        if plan_path.exists():
            data = json.loads(plan_path.read_text())
            run_id = run_dir.name
            if store.get_run(run_id):
                continue
            started = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).isoformat()
            store.create_run(run_id, "plan_execute_synthesis", data.get("goal", run_id)[:120], started)
            goal = data.get("goal", "")
            store.upsert_step(
                RunStepEvent(
                    run_id=run_id,
                    step_id=f"{run_id}-plan",
                    parent_step_id=None,
                    arm="plan_execute_synthesis",
                    type="plan",
                    status="success",
                    title=f"Plan: {len(data.get('subtasks', []))} steps",
                    started_at=started,
                    ended_at=started,
                    payload=StepPayload(result={"goal": goal, "steps": data.get("subtasks", [])}),
                )
            )
            for step in data.get("subtasks", []):
                tool_hint = step.get("tool_hint", "")
                step_type = "browser_step" if tool_hint in ("browser_use", "browser-use") else (
                    "reflection" if tool_hint == "none" else "tool_call"
                )
                evt = RunStepEvent(
                    run_id=run_id,
                    step_id=f"{run_id}-step-{step.get('id')}",
                    parent_step_id=None,
                    arm="plan_execute_synthesis",
                    type=step_type,  # type: ignore[arg-type]
                    status="success" if step.get("status") == "DONE" else "failed",
                    title=f"{tool_hint}: {(step.get('task') or '')[:80]}",
                    started_at=started,
                    ended_at=started,
                    payload=StepPayload(
                        args={"task": step.get("task"), "tool_hint": tool_hint},
                        result=step.get("result"),
                        error=step.get("error"),
                        tool_name=tool_hint,
                        model=_parse_browser_model(step.get("result")) if step_type == "browser_step" else None,
                    ),
                )
                store.upsert_step(evt)
            store.update_run_status(run_id, "success", pass_fail=True, ended_at=utc_now_iso())
            imported += 1
        elif react_path.exists():
            data = json.loads(react_path.read_text())
            run_id = run_dir.name
            if store.get_run(run_id):
                continue
            goal = data.get("goal", run_id)
            started = datetime.fromtimestamp(run_dir.stat().st_mtime, tz=timezone.utc).isoformat()
            store.create_run(run_id, "react", goal[:120], started)
            for i, turn in enumerate(data.get("history", []), start=1):
                evt = RunStepEvent(
                    run_id=run_id,
                    step_id=f"{run_id}-react-{i}",
                    parent_step_id=None,
                    arm="react",
                    type="tool_call" if turn.get("action") else "reflection",
                    status="success",
                    title=turn.get("action") or turn.get("thought", "")[:80],
                    started_at=started,
                    ended_at=started,
                    payload=StepPayload(
                        args={"action_input": turn.get("action_input")},
                        result=turn.get("observation"),
                        tool_name=turn.get("action"),
                    ),
                )
                store.upsert_step(evt)
            store.update_run_status(run_id, "success", pass_fail=True, ended_at=utc_now_iso())
            imported += 1
    return imported


class _PlanShim:
    def __init__(self, data: dict) -> None:
        self.goal = data.get("goal", "")
        self.subtasks = [_StepShim(s) for s in data.get("subtasks", [])]


class _StepShim:
    def __init__(self, data: dict) -> None:
        self.id = data.get("id")
        self.task = data.get("task", "")
        self.tool_hint = data.get("tool_hint", "")
        self.status = data.get("status", "DONE")
        self.result = data.get("result")
        self.error = data.get("error")


async def execute_run_async(
    run_id: str,
    task: str,
    arm: ArmName,
    store: RunStore,
    auto_approve: bool = True,
) -> None:
    loop = asyncio.get_running_loop()
    tracker = RunTracker(run_id, arm, store)
    tracker.bind_loop(loop)

    def emit_callback(event: RunStepEvent) -> None:
        tracker.handle_event(event)

    token = set_emitter(emit_callback)
    ctx_tokens = set_run_context(run_id, arm)
    start = time.monotonic()
    store.create_run(run_id, arm, task[:120])

    try:
        await loop.run_in_executor(
            None,
            lambda: _run_graph_blocking(run_id, task, arm, tracker, auto_approve),
        )
        elapsed_ms = int((time.monotonic() - start) * 1000)
        store.update_run_status(
            run_id, "success", duration_ms=elapsed_ms, pass_fail=True, ended_at=utc_now_iso()
        )
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        store.update_run_status(
            run_id, "failed", duration_ms=elapsed_ms, pass_fail=False, ended_at=utc_now_iso()
        )
        tracker.handle_event(
            RunStepEvent(
                run_id=run_id,
                step_id=f"{run_id}-error",
                parent_step_id=None,
                arm=arm,
                type="tool_result",
                status="failed",
                title="Run failed",
                started_at=utc_now_iso(),
                ended_at=utc_now_iso(),
                payload=StepPayload(error=str(exc)),
            )
        )
    finally:
        reset_emitter(token)
        reset_run_context(ctx_tokens)
        await event_bus.close_run(run_id)


def _run_graph_blocking(
    run_id: str,
    task: str,
    arm: ArmName,
    tracker: RunTracker,
    auto_approve: bool,
) -> None:
    if arm == "react":
        _run_react(task, tracker, auto_approve)
    else:
        disable_synthesis = arm == "plan_execute"
        _run_plan_execute(task, tracker, disable_synthesis, auto_approve)


def _run_react(task: str, tracker: RunTracker, auto_approve: bool) -> None:
    from src.agents.react.state import ReactState
    from src.agents.react.graph import build_react_graph

    graph = build_react_graph()
    state: ReactState = {
        "goal": task,
        "history": [],
        "final_answer": None,
        "iterations": 0,
        "workspace_path": None,
    }
    config = {"configurable": {"thread_id": f"viz-{uuid.uuid4()}"}}

    for update in graph.stream(state, config, stream_mode="updates"):
        for node_name, node_state in update.items():
            tracker.update_from_state(node_state, node_name)


def _run_plan_execute(
    task: str,
    tracker: RunTracker,
    disable_synthesis: bool,
    auto_approve: bool,
) -> None:
    import sqlite3
    from contextlib import closing

    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.types import Command

    from src.agents.plan_execute.graph import build_graph
    from src.agents.plan_execute.state import State, StepStatus

    patched_module = None
    original_synth = None
    if disable_synthesis:
        import src.agents.plan_execute.graph as graph_module

        def _disabled(state: State) -> dict:
            plan = state["plan"]
            if plan is None:
                return {"plan": plan}
            running = next((s for s in plan.subtasks if s.status == StepStatus.RUNNING), None)
            if running is not None:
                running.status = StepStatus.FAILED
                running.error = "Synthesis disabled for plan_execute arm."
            return {"plan": plan, "steps_executed": 1}

        patched_module = graph_module
        original_synth = graph_module.synthesize_tool_node
        graph_module.synthesize_tool_node = _disabled

    try:
        graph = build_graph()
        initial: State = {
            "input": task,
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
        config = {"configurable": {"thread_id": f"viz-{uuid.uuid4()}"}}
        serializer = JsonPlusSerializer(
            allowed_msgpack_modules=[
                ("src.agents.plan_execute.state", "StepStatus"),
                ("src.agents.plan_execute.state", "Plan"),
            ]
        )

        with closing(sqlite3.connect("checkpoints.db", check_same_thread=False)) as conn:
            checkpointer = SqliteSaver(conn, serde=serializer)
            compiled = graph.compile(checkpointer=checkpointer)
            result = compiled.invoke(initial, config)

            while "__interrupt__" in result:
                if auto_approve:
                    response = {"decision": "approve"}
                else:
                    raise RuntimeError("Run interrupted — approval required")
                result = compiled.invoke(Command(resume=response), config)

            for update in compiled.stream(result, config, stream_mode="updates"):
                for node_name, node_state in update.items():
                    tracker.update_from_state(node_state, node_name)
    finally:
        if patched_module is not None and original_synth is not None:
            patched_module.synthesize_tool_node = original_synth
