"""Regression tests for replaner logic and state management."""

import pytest
from src.agents.plan_execute.nodes import replaner, MAX_REPLAN
from src.agents.plan_execute.tools import MAX_REPLAN_CONTEXT_CHARS, bound_replan_context
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def test_replan_count_accumulates():
    """
    Direct regression test for the reducer bug.
    Test that the sum_replan_count reducer correctly accumulates values.
    """
    from src.agents.plan_execute.state import sum_replan_count
    
    # Test the reducer directly
    existing_count = 2
    new_delta = 1
    result = sum_replan_count(existing_count, new_delta)
    
    assert result == 3, f"Expected reducer to sum 2 + 1 = 3, got {result}"
    
    # Test that it accumulates across multiple calls
    result2 = sum_replan_count(result, 1)
    assert result2 == 4, f"Expected reducer to sum 3 + 1 = 4, got {result2}"


def test_max_replan_guard_terminates():
    """
    MAX_REPLAN guard actually terminates.
    Force replan_count >= MAX_REPLAN, assert remaining PENDING/RUNNING steps get
    marked CANCELLED and moved to plan.cancelled_steps (not left in subtasks as
    FAILED — FAILED implies "attempted and broke", which is misleading for a
    step that never actually ran). breakdown_task must NOT be called (no wasted
    LLM call once terminated).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.RUNNING),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": MAX_REPLAN  # At the limit
    }
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        result = replaner(state)
        
        # breakdown_task should NOT be called (no wasted LLM call)
        mock_breakdown.assert_not_called()

        # DONE step remains in subtasks, unaffected
        assert len(result["plan"].subtasks) == 1
        assert result["plan"].subtasks[0].status == StepStatus.DONE

        # PENDING and RUNNING steps should be CANCELLED and moved out of
        # subtasks into cancelled_steps
        assert len(result["plan"].cancelled_steps) == 2
        cancelled_ids = {s.id for s in result["plan"].cancelled_steps}
        assert cancelled_ids == {2, 3}
        for step in result["plan"].cancelled_steps:
            assert step.status == StepStatus.CANCELLED
            assert "Replan limit" in step.error
            assert "exceeded" in step.error.lower()


def test_done_steps_preserved_renumbered():
    """
    DONE steps are preserved and renumbered correctly after a replan.
    Assert step IDs stay sequential, no duplicate IDs, DONE steps' results survive into the new plan.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0
    }
    
    mock_new_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised step 3", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="new step 4", tool_hint="web_search", status=StepStatus.PENDING)
        ]
    )
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_new_plan
        
        result = replaner(state)
        
        # Check that DONE step is preserved
        assert len(result["plan"].subtasks) == 3  # 1 DONE + 2 new
        
        # Check that DONE step result survived
        done_step = result["plan"].subtasks[0]
        assert done_step.status == StepStatus.DONE
        assert done_step.result == "Result 1"
        
        # Check that step IDs are sequential (1, 2, 3)
        step_ids = [s.id for s in result["plan"].subtasks]
        assert step_ids == [1, 2, 3], f"Expected sequential IDs [1, 2, 3], got {step_ids}"
        
        # Check no duplicate IDs
        assert len(step_ids) == len(set(step_ids)), "Step IDs should be unique"


def test_failed_steps_dropped():
    """
    FAILED steps are dropped from the new plan (not carried forward to fail again).
    This is the exact mechanism from the last trace; worth locking in explicitly.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0
    }
    
    mock_new_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised step 3", tool_hint="web_search", status=StepStatus.PENDING)
        ]
    )
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_new_plan
        
        result = replaner(state)
        
        # FAILED step should not be in the new plan
        failed_steps = [s for s in result["plan"].subtasks if s.status == StepStatus.FAILED]
        assert len(failed_steps) == 0, "FAILED steps should be dropped from new plan"
        
        # Only DONE and new PENDING steps should remain
        assert len(result["plan"].subtasks) == 2  # 1 DONE + 1 new


def test_replaner_with_no_done_steps():
    """
    Test replaner when there are no DONE steps (first step fails immediately).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0
    }
    
    mock_new_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised step 1", tool_hint="web_search", status=StepStatus.PENDING)
        ]
    )
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_new_plan
        
        result = replaner(state)
        
        # Should still work, just no DONE steps to preserve
        assert len(result["plan"].subtasks) == 1
        assert result["plan"].subtasks[0].status == StepStatus.PENDING


def test_replaner_none_plan_raises():
    """
    Test that replaner raises RuntimeError when called with no plan in state.
    """
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="replaner called with no plan"):
        replaner(state)


def test_replaner_context_passed_to_breakdown_task():
    """
    Test that completed step results are passed as context to breakdown_task.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0
    }
    
    mock_new_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised step", tool_hint="web_search", status=StepStatus.PENDING)
        ]
    )
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_new_plan
        
        replaner(state)
        
        # Verify breakdown_task was called with context
        call_args = mock_breakdown.call_args
        context = call_args[1].get('context')
        
        assert context is not None, "breakdown_task should receive context"
        assert len(context) > 0, "Context should not be empty"
        
        # Context should contain both DONE and FAILED step information
        context_str = " ".join(context)
        assert "Result 1" in context_str, "Context should contain DONE step result"
        assert "API timeout" in context_str, "Context should contain FAILED step error"


def test_replan_context_is_bounded_before_calling_planner():
    """Large tool payloads must not be concatenated into an unbounded prompt."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="large result", tool_hint="web_search", status=StepStatus.DONE, result="x" * 50_000),
            Step(id=2, task="failed step", tool_hint="web_search", status=StepStatus.FAILED, error="timeout"),
        ],
    )
    new_plan = Plan(
        goal="test goal",
        subtasks=[Step(id=1, task="revised step", tool_hint="web_search", status=StepStatus.PENDING)],
    )
    state: State = {"input": "test", "plan": plan, "replan_count": 0}

    with patch("src.agents.plan_execute.nodes.breakdown_task", return_value=new_plan) as mock_breakdown:
        result = replaner(state)

    context = mock_breakdown.call_args.kwargs["context"]
    assert len("\n".join(context)) <= MAX_REPLAN_CONTEXT_CHARS
    assert "characters omitted" in "\n".join(context)
    assert len("\n".join(result["last_replan_context"])) <= MAX_REPLAN_CONTEXT_CHARS


def test_bound_replan_context_preserves_short_records():
    context = ["Step 1: useful result", "Step 2: timeout"]
    assert bound_replan_context(context) == context


def test_replaner_returns_delta():
    """
    Test that replaner returns delta of 1 for replan_count (which the reducer will sum).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
        ]
    )
    state: State = {
        "input": "test",
        "plan": plan,
        "replan_count": 0
    }
    
    mock_new_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised step", tool_hint="web_search", status=StepStatus.PENDING)
        ]
    )
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_new_plan
        
        result = replaner(state)
        
        # Should return delta of 1 for replan_count
        assert result["replan_count"] == 1, "replaner should return delta of 1"
