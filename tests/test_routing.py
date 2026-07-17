"""Regression tests for graph.py conditional edge routing logic."""

import pytest
from src.agents.plan_execute.graph import _route_to_tool, _route_after_tool
from src.agents.plan_execute.state import State, Plan, Step, StepStatus


def test_tool_hint_none_routes_to_reason():
    """
    Regression test for premature-synthesis bug and silent-stub bug.
    tool_hint == "none" should route to reason_node, not stub or synthesize.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="reasoning step", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = _route_to_tool(state)
    
    assert result == "reason", f"Expected 'reason', got '{result}'"


def test_tool_hint_none_mid_plan_no_short_circuit():
    """
    Regression test for premature-synthesis bug.
    tool_hint == "none" mid-plan should NOT short-circuit remaining PENDING steps.
    Build a 4-step plan where step 2 is tool_hint="none", assert steps 3-4 still execute after it.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="reasoning step", tool_hint="none", status=StepStatus.RUNNING),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=4, task="step 4", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = _route_to_tool(state)
    
    # Should route to reason, not synthesize (which would skip steps 3-4)
    assert result == "reason", f"Expected 'reason' to continue execution, got '{result}'"


def test_synthesis_only_when_no_running_step():
    """
    Regression test for premature-synthesis bug.
    Synthesis should only trigger once no RUNNING step remains (all steps DONE/FAILED).
    """
    # Case 1: No RUNNING step, all DONE -> should synthesize
    plan_done = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.DONE),
        ]
    )
    state_done: State = {"input": "test", "plan": plan_done}
    
    result_done = _route_to_tool(state_done)
    assert result_done == "synthesize", f"Expected 'synthesize' when all steps DONE, got '{result_done}'"
    
    # Case 2: No RUNNING step, mix of DONE/FAILED -> should synthesize
    plan_mixed = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED),
        ]
    )
    state_mixed: State = {"input": "test", "plan": plan_mixed}
    
    result_mixed = _route_to_tool(state_mixed)
    assert result_mixed == "synthesize", f"Expected 'synthesize' when no RUNNING steps, got '{result_mixed}'"
    
    # Case 3: Has RUNNING step -> should NOT synthesize
    plan_running = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.RUNNING),
        ]
    )
    state_running: State = {"input": "test", "plan": plan_running}
    
    result_running = _route_to_tool(state_running)
    assert result_running != "synthesize", f"Should not synthesize when RUNNING step exists, got '{result_running}'"


def test_web_search_routes_to_tavily():
    """
    Test that web_search/tavily_search hints route to tavily_search_node.
    """
    # Test "web_search"
    plan_web = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state_web: State = {"input": "test", "plan": plan_web}
    
    result_web = _route_to_tool(state_web)
    assert result_web == "tavily_search", f"Expected 'tavily_search' for web_search, got '{result_web}'"
    
    # Test "tavily_search"
    plan_tavily = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step", tool_hint="tavily_search", status=StepStatus.RUNNING)
        ]
    )
    state_tavily: State = {"input": "test", "plan": plan_tavily}
    
    result_tavily = _route_to_tool(state_tavily)
    assert result_tavily == "tavily_search", f"Expected 'tavily_search' for tavily_search, got '{result_tavily}'"


def test_unknown_hints_route_to_stub():
    """
    Test that unknown tool hints route to stub_node.
    """
    unknown_hints = ["file_editor", "database", "api_call"]
    
    for hint in unknown_hints:
        plan = Plan(
            goal="test goal",
            subtasks=[
                Step(id=1, task="unknown step", tool_hint=hint, status=StepStatus.RUNNING)
            ]
        )
        state: State = {"input": "test", "plan": plan}
        
        result = _route_to_tool(state)
        assert result == "stub", f"Expected 'stub' for hint '{hint}', got '{result}'"


def test_code_executor_routes_to_code_executor_node():
    """
    Test that code_executor hint routes to code_executor_node (not stub).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="execute python code", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = _route_to_tool(state)
    assert result == "code_executor", f"Expected 'code_executor' for code_executor hint, got '{result}'"


def test_route_after_tool_failed_step():
    """
    Test that _route_after_tool routes to replaner when any step fails.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = _route_after_tool(state)
    assert result == "replaner", f"Expected 'replaner' on FAILED step, got '{result}'"


def test_route_after_tool_all_success():
    """
    Test that _route_after_tool routes back to executor when all steps succeed.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.DONE),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = _route_after_tool(state)
    assert result == "executor", f"Expected 'executor' on success, got '{result}'"


def test_route_after_tool_none_plan():
    """
    Test that _route_after_tool handles None plan gracefully.
    """
    state: State = {"input": "test", "plan": None}
    
    result = _route_after_tool(state)
    assert result == "executor", f"Expected 'executor' for None plan, got '{result}'"
