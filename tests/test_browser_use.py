"""Unit tests for the Browser Use/OpenRouter integration (no real browser)."""

import pytest

from src.agents.plan_execute import nodes
from src.agents.plan_execute.graph import _route_after_approval, _route_to_tool
from src.agents.plan_execute.state import Plan, Step, StepStatus
from src.tools.browser_use.config import BROWSER_MODEL, BrowserUseConfig
from src.tools.browser_use.runner import BrowserTaskResult, run_browser_task


@pytest.mark.asyncio
async def test_runner_uses_openrouter_ling_in_text_only_mode(monkeypatch):
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
    assert f"model={BROWSER_MODEL}" in plan.subtasks[0].result
    assert result["steps_executed"] == 1


def test_browser_use_navigation_failure_404(monkeypatch):
    """Test browser use handles 404 navigation errors gracefully."""
    plan = Plan(
        goal="Read a page",
        subtasks=[Step(id=1, task="Navigate to non-existent page", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("Navigation failed: 404 Not Found")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "404" in plan.subtasks[0].error or "Navigation failed" in plan.subtasks[0].error


def test_browser_use_navigation_timeout(monkeypatch):
    """Test browser use handles navigation timeout gracefully."""
    plan = Plan(
        goal="Read a slow page",
        subtasks=[Step(id=1, task="Navigate to slow page", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise TimeoutError("Navigation timed out after 30s")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "timeout" in plan.subtasks[0].error.lower()


def test_browser_use_element_not_found(monkeypatch):
    """Test browser use handles element not found errors."""
    plan = Plan(
        goal="Click a button",
        subtasks=[Step(id=1, task="Click non-existent button", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("Element not found: selector '.non-existent-button'")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "Element not found" in plan.subtasks[0].error


def test_browser_use_screenshot_failure(monkeypatch):
    """Test browser use handles screenshot capture failures."""
    plan = Plan(
        goal="Take a screenshot",
        subtasks=[Step(id=1, task="Capture page screenshot", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("Screenshot failed: display not available")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "Screenshot" in plan.subtasks[0].error


def test_browser_use_model_api_failure(monkeypatch):
    """Test browser use handles model API failures."""
    plan = Plan(
        goal="Analyze page content",
        subtasks=[Step(id=1, task="Read page with vision model", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("Model API error: rate limit exceeded")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "Model API" in plan.subtasks[0].error or "rate limit" in plan.subtasks[0].error


def test_browser_use_browser_crash(monkeypatch):
    """Test browser use handles browser crash scenarios."""
    plan = Plan(
        goal="Navigate to page",
        subtasks=[Step(id=1, task="Navigate with crashed browser", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("Browser crashed: segmentation fault")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "crash" in plan.subtasks[0].error.lower()


def test_browser_use_multiple_tabs(monkeypatch):
    """Test browser use handles multiple tab scenarios."""
    plan = Plan(
        goal="Compare pages across tabs",
        subtasks=[Step(id=1, task="Open multiple tabs and compare", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        return BrowserTaskResult("Compared 3 tabs successfully", BROWSER_MODEL, False, "openrouter")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.DONE
    assert "Compared" in plan.subtasks[0].result


def test_browser_use_dns_error(monkeypatch):
    """Test browser use handles DNS resolution errors."""
    plan = Plan(
        goal="Navigate to invalid domain",
        subtasks=[Step(id=1, task="Navigate to non-existent domain", tool_hint="browser_use", status=StepStatus.RUNNING)],
    )

    def fake_run(task):
        raise Exception("DNS resolution failed: NXDOMAIN")

    monkeypatch.setattr(nodes, "run_browser_task_sync", fake_run)
    result = nodes.browser_use_node({"input": plan.goal, "plan": plan})

    assert plan.subtasks[0].status == StepStatus.FAILED
    assert "DNS" in plan.subtasks[0].error or "NXDOMAIN" in plan.subtasks[0].error
