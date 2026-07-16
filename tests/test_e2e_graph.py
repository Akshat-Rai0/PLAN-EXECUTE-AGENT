"""End-to-end graph execution regression tests."""

import pytest
from src.agents.plan_execute.graph import build_graph
from src.agents.plan_execute.nodes import replaner
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def test_successful_3_step_execution():
    """
    One fully-mocked run: 3-step plan, all searches "succeed and are relevant".
    Assert final state has plan.final_answer set and all steps DONE.
    """
    # Mock the plan generation
    mock_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step 1", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="search step 2", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=3, task="search step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    
    # Create proper mock response objects
    class MockResponse:
        def __init__(self, content):
            self.content = content
    
    mock_synthesis_response = MockResponse("Final synthesized answer")
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_plan
        
        with patch('src.agents.plan_execute.nodes.tavily_search') as mock_search:
            mock_search.return_value = "Search result"
            
            with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
                mock_relevance.return_value = (True, "Relevant")
                
                with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
                    mock_llm = MagicMock()
                    mock_llm.invoke.return_value = mock_synthesis_response
                    mock_get_llm.return_value = mock_llm
                    
                    graph = build_graph()
                    initial_state: State = {
                        "input": "test goal",
                        "plan": None
                    }
                    
                    config = {"configurable": {"thread_id": "test-thread"}}
                    result = graph.invoke(initial_state, config)
                    
                    # Verify final state
                    assert result["plan"] is not None
                    assert result["plan"].final_answer == "Final synthesized answer"
                    
                    # Verify all steps are DONE
                    for step in result["plan"].subtasks:
                        assert step.status == StepStatus.DONE, f"Step {step.id} should be DONE, got {step.status}"


def test_failed_replan_success_cycle():
    """
    One fully-mocked run with one FAILED→replan→success cycle.
    Assert exactly one replan occurred, replan_count == 1, and the run still completes.
    """
    # Initial plan that will fail on step 2
    initial_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step 1", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="search step 2", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=3, task="search step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    
    # Replan after failure (only step 2 and 3)
    replan_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="revised search step 2", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="revised search step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    
    # Create proper mock response objects
    class MockResponse:
        def __init__(self, content):
            self.content = content
    
    mock_synthesis_response = MockResponse("Final answer after replan")
    
    breakdown_call_count = [0]
    
    def breakdown_side_effect(goal, context=None):
        breakdown_call_count[0] += 1
        if breakdown_call_count[0] == 1:
            return initial_plan
        else:
            return replan_plan
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.side_effect = breakdown_side_effect
        
        with patch('src.agents.plan_execute.nodes.tavily_search') as mock_search:
            # First call succeeds, second call fails (triggers replan), subsequent calls succeed
            search_call_count = [0]
            
            def search_side_effect(query, search_depth=None):
                search_call_count[0] += 1
                if search_call_count[0] == 2:
                    raise Exception("Search timeout")
                return "Search result"
            
            mock_search.side_effect = search_side_effect
            
            with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
                mock_relevance.return_value = (True, "Relevant")
                
                with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
                    mock_llm = MagicMock()
                    mock_llm.invoke.return_value = mock_synthesis_response
                    mock_get_llm.return_value = mock_llm
                    
                    graph = build_graph()
                    initial_state: State = {
                        "input": "test goal",
                        "plan": None
                    }
                    
                    config = {"configurable": {"thread_id": "test-thread"}}
                    result = graph.invoke(initial_state, config)
                    
                    # Verify exactly one replan occurred
                    assert breakdown_call_count[0] == 2, f"Expected 2 breakdown_task calls (initial + 1 replan), got {breakdown_call_count[0]}"
                    assert result["replan_count"] == 1, f"Expected replan_count == 1, got {result['replan_count']}"
                    
                    # Verify run completed successfully
                    assert result["plan"] is not None
                    assert result["plan"].final_answer == "Final answer after replan"
                    
                    # Verify final state has all steps DONE (after replan)
                    done_count = sum(1 for step in result["plan"].subtasks if step.status == StepStatus.DONE)
                    assert done_count == len(result["plan"].subtasks), "All steps should be DONE after successful replan"


def test_e2e_with_reason_node():
    """
    End-to-end test with a reason_node step (tool_hint="none").
    Verifies that reason_node is properly integrated into the graph flow.
    """
    # Plan with a reasoning step in the middle
    mock_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step 1", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="reasoning step", tool_hint="none", status=StepStatus.PENDING),
            Step(id=3, task="search step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    
    # Create proper mock response objects
    class MockResponse:
        def __init__(self, content):
            self.content = content
    
    mock_response = MockResponse("Mock response")
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_plan
        
        with patch('src.agents.plan_execute.nodes.tavily_search') as mock_search:
            mock_search.return_value = "Search result"
            
            with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
                mock_relevance.return_value = (True, "Relevant")
                
                with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
                    mock_llm = MagicMock()
                    mock_llm.invoke.return_value = mock_response
                    mock_get_llm.return_value = mock_llm
                    
                    graph = build_graph()
                    initial_state: State = {
                        "input": "test goal",
                        "plan": None
                    }
                    
                    config = {"configurable": {"thread_id": "test-thread"}}
                    result = graph.invoke(initial_state, config)
                    
                    # Verify final state
                    assert result["plan"] is not None
                    assert result["plan"].final_answer is not None
                    
                    # Verify reasoning step has a real result (not stub)
                    reasoning_step = result["plan"].subtasks[1]
                    assert reasoning_step.result is not None
                    assert "[stub]" not in reasoning_step.result
                    
                    # Verify all steps are DONE
                    for step in result["plan"].subtasks:
                        assert step.status == StepStatus.DONE


def test_e2e_max_replan_termination():
    """
    End-to-end test that verifies MAX_REPLAN guard terminates execution.
    Simplified to avoid msgpack serialization issues with MagicMock.

    PENDING/RUNNING steps at termination should be CANCELLED and moved to
    plan.cancelled_steps, not left in subtasks marked FAILED.
    """
    # Test the guard logic directly at the node level instead of full graph
    from src.agents.plan_execute.nodes import MAX_REPLAN
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.PENDING),
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

        # PENDING step should be CANCELLED and moved to cancelled_steps
        assert len(result["plan"].subtasks) == 1
        assert len(result["plan"].cancelled_steps) == 1
        cancelled_step = result["plan"].cancelled_steps[0]
        assert cancelled_step.status == StepStatus.CANCELLED
        assert "Replan limit" in cancelled_step.error


def test_e2e_tool_hint_none_mid_plan():
    """
    Regression test for premature-synthesis bug in full graph context.
    tool_hint="none" mid-plan should not short-circuit to synthesis.
    """
    # Plan with tool_hint="none" in the middle
    mock_plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step 1", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="reasoning step", tool_hint="none", status=StepStatus.PENDING),
            Step(id=3, task="search step 3", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    
    # Create proper mock response objects
    class MockResponse:
        def __init__(self, content):
            self.content = content
    
    mock_reason_response = MockResponse("Reasoning result")
    mock_synthesis_response = MockResponse("Final answer")
    
    with patch('src.agents.plan_execute.nodes.breakdown_task') as mock_breakdown:
        mock_breakdown.return_value = mock_plan
        
        with patch('src.agents.plan_execute.nodes.tavily_search') as mock_search:
            mock_search.return_value = "Search result"
            
            with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
                mock_relevance.return_value = (True, "Relevant")
                
                with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
                    mock_llm = MagicMock()
                    
                    llm_call_count = [0]
                    
                    def llm_side_effect(messages):
                        llm_call_count[0] += 1
                        # Return synthesis response for all calls after the first reasoning call
                        if llm_call_count[0] == 1:
                            return mock_reason_response
                        else:
                            return mock_synthesis_response
                    
                    mock_llm.invoke.side_effect = llm_side_effect
                    mock_get_llm.return_value = mock_llm
                    
                    graph = build_graph()
                    initial_state: State = {
                        "input": "test goal",
                        "plan": None
                    }
                    
                    config = {"configurable": {"thread_id": "test-thread"}}
                    result = graph.invoke(initial_state, config)
                    
                    # Verify all 3 steps executed (step 3 should not be skipped)
                    assert len(result["plan"].subtasks) == 3, "All 3 steps should be present"
                    
                    # Verify step 3 (after reasoning step) was executed
                    step_3 = result["plan"].subtasks[2]
                    assert step_3.status == StepStatus.DONE, "Step 3 should be DONE, not skipped"
                    
                    # Verify reasoning step has a real result (not stub)
                    reasoning_step = result["plan"].subtasks[1]
                    assert reasoning_step.result == "Reasoning result"
                    assert "[stub]" not in reasoning_step.result
