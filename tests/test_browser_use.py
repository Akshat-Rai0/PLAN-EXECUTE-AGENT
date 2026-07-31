"""Unit tests for the Browser Use/OpenRouter integration (no real browser)."""

import pytest

from src.agents.plan_execute import nodes
from src.agents.plan_execute.graph import _route_after_approval, _route_to_tool
from src.agents.plan_execute.state import Plan, Step, StepStatus
from src.tools.browser_use.config import BROWSER_MODEL, BrowserUseConfig
from src.tools.browser_use.runner import BrowserTaskResult, run_browser_task


@pytest.mark.asyncio
async def test_runner_uses_openrouter_gemma_in_text_only_mode(monkeypatch):
    calls = []

    async def fake_run(task, *, config):
        calls.append(config.model)
        return "browser result"

    monkeypatch.setattr("src.tools.browser_use.runner._run_with_model", fake_run)
    config = BrowserUseConfig(api_key="test-key")

    result = await run_browser_task("read a page", config)

    assert calls == [BROWSER_MODEL]
    assert result == BrowserTaskResult(
        result="browser result",
        model=BROWSER_MODEL,
        use_vision=False,
        provider="openrouter",
    )


def test_browser_use_routes_through_approval_then_browser_node():
    plan = Plan(
        goal="Compare two products in their rendered web pages",
        subtasks=[Step(id=1, task="Compare product pages", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )
    state = {"input": plan.goal, "plan": plan}

    assert _route_to_tool(state) == "approval"
    assert _route_after_approval(state) == "browser_use"


def test_browser_node_uses_read_only_policy_and_records_model(monkeypatch):
    plan = Plan(
        goal="Compare two products",
        subtasks=[Step(id=1, task="Read displayed prices", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )
    captured = {}

    def fake_run(task):
        captured["task"] = task
        return BrowserTaskResult("Product A is cheaper.", BROWSER_MODEL, False, "openrouter")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert "This is a read-only task" in captured["task"]
    assert plan.subtasks[0].status == StepStatus.DONE
    assert "model=google/gemma-4-31b-it:free" in plan.subtasks[0].result
    assert result["steps_executed"] == 1
