"""Persistence for the durable artifacts produced by a CLI agent run."""

from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import shutil
from typing import Optional, Sequence

from .state import Plan

OUTPUT_DIRECTORY_NAME = "agent_outputs"
_WORKSPACE_IGNORE = shutil.ignore_patterns(
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "*.pyc",
)


def _goal_slug(goal: str, max_length: int = 56) -> str:
    """Create a readable, filesystem-safe label for a goal."""
    words = "".join(char.lower() if char.isalnum() else " " for char in goal).split()
    slug = "-".join(words)[:max_length].strip("-")
    return slug or "agent-run"


def _create_run_directory(output_root: Path, goal: str, started_at: datetime) -> Path:
    """Create a collision-free, labelled directory for one execution."""
    output_root.mkdir(parents=True, exist_ok=True)
    base_name = f"{started_at.strftime('%Y%m%d-%H%M%S')}_{_goal_slug(goal)}"
    candidate = output_root / base_name
    suffix = 2
    while candidate.exists():
        candidate = output_root / f"{base_name}-{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def _run_summary(plan: Plan, workspace_copied: bool, server_url: Optional[str]) -> str:
    """Produce a compact human-readable index beside the complete plan JSON."""
    lines = [
        f"# Agent run: {plan.goal}",
        "",
        "## Final answer",
        plan.final_answer or "No synthesized final answer was produced.",
        "",
        "## Steps",
    ]
    for step in plan.subtasks:
        lines.extend(
            [
                f"### {step.id}. {step.task}",
                f"- Tool: `{step.tool_hint}`",
                f"- Status: `{step.status.value}`",
            ]
        )
        if step.error:
            lines.append(f"- Error: {step.error}")

    lines.extend(["", "## Artifacts"])
    lines.append(
        "- Generated workspace files: [`workspace/`](workspace/)"
        if workspace_copied
        else "- No generated workspace files for this run."
    )
    if server_url:
        lines.append(f"- Development server URL during the run: {server_url}")
    lines.extend(
        [
            "- Complete plan, step results, and raw tool output: [`plan.json`](plan.json)",
            "",
        ]
    )
    return "\n".join(lines)


def persist_run_artifacts(
    repo_root: str | Path,
    plan: Plan,
    workspace_path: Optional[str] = None,
    server_url: Optional[str] = None,
    started_at: Optional[datetime] = None,
) -> Path:
    """Persist a run's plan, summary, and generated source files at repo root.

    Code executes in a temporary sandbox workspace for safety. After a run
    completes, this function copies the useful project files into the durable
    ``agent_outputs/<timestamp>_<goal>/workspace`` handoff directory. Package
    install/cache directories are deliberately omitted because they are
    reproducible dependencies rather than generated deliverables.
    """
    repo_root = Path(repo_root).resolve()
    run_dir = _create_run_directory(
        repo_root / OUTPUT_DIRECTORY_NAME,
        plan.goal,
        started_at or datetime.now().astimezone(),
    )

    (run_dir / "plan.json").write_text(plan.model_dump_json(indent=2) + "\n", encoding="utf-8")

    workspace_copied = False
    if workspace_path:
        source_workspace = Path(workspace_path)
        if source_workspace.is_dir():
            shutil.copytree(source_workspace, run_dir / "workspace", ignore=_WORKSPACE_IGNORE)
            workspace_copied = True

    (run_dir / "summary.md").write_text(
        _run_summary(plan, workspace_copied=workspace_copied, server_url=server_url),
        encoding="utf-8",
    )
    return run_dir


def persist_react_run_artifacts(
    repo_root: str | Path,
    goal: str,
    final_answer: Optional[str],
    iterations: int,
    history: Sequence[object],
    started_at: Optional[datetime] = None,
) -> Path:
    """Persist a ReAct run in the same root-level output structure."""
    repo_root = Path(repo_root).resolve()
    run_dir = _create_run_directory(
        repo_root / OUTPUT_DIRECTORY_NAME,
        goal,
        started_at or datetime.now().astimezone(),
    )
    turns = [
        {
            "thought": turn.thought,
            "action": turn.action,
            "action_input": turn.action_input,
            "observation": turn.observation,
        }
        for turn in history
    ]
    result = {
        "agent": "react",
        "goal": goal,
        "final_answer": final_answer,
        "iterations": iterations,
        "history": turns,
    }
    (run_dir / "react-trace.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )

    lines = [
        f"# ReAct run: {goal}",
        "",
        "## Final answer",
        final_answer or "No final answer was produced.",
        "",
        "## Metrics",
        f"- Total iterations (LLM calls): {iterations}",
        "",
        "## Turns",
    ]
    for index, turn in enumerate(turns, start=1):
        lines.extend(
            [
                f"### {index}. {turn['action']}",
                f"- Thought: {turn['thought']}",
                f"- Action input: {turn['action_input']}",
            ]
        )
    lines.extend(["", "- Complete turn history and raw observations: [`react-trace.json`](react-trace.json)", ""])
    (run_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")
    return run_dir
