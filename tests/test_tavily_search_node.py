"""Regression tests for tavily_search_node execution and context extraction."""

import pytest
from src.agents.plan_execute.nodes import tavily_search_node, _extract_search_context
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def test_query_includes_goal_and_task():
    """
    Test that query includes the goal + step task (baseline behavior).
    """
    plan = Plan(
        goal="Plan a weekend trip to Goa",
        subtasks=[
            Step(id=1, task="search for Goa weather", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_search_result = "Weather in Goa: Sunny, 32°C"
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = mock_search_result
        
        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")
            
            tavily_search_node(state)
            
            # Verify the query format
            call_args = mock_tavily_search.call_args
            query = call_args[0][0]
            
            assert "Plan a weekend trip to Goa" in query, "Query should include goal"
            assert "search for Goa weather" in query, "Query should include step task"


def test_extract_search_context_surfaces_year():
    """
    Unit test _extract_search_context correctly surfaces a year from a prior short result.
    Direct unit test of the helper, isolated from the graph.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="determine current year", tool_hint="none", status=StepStatus.DONE, result="The current year is 2026."),
            Step(id=2, task="search for events", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    
    current_step = plan.subtasks[1]
    context = _extract_search_context(plan, current_step)
    
    assert "2026" in context, "Year from prior result should be surfaced in context"


def test_extract_search_context_does_not_fold_long_result():
    """
    Unit test _extract_search_context does NOT fold in a long prior result (the >200 char guard).
    Regression test for "don't stuff noisy search text into the next query."
    """
    long_result = "A" * 250  # Longer than _SHORT_RESULT_CHAR_LIMIT (200)
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="long search", tool_hint="web_search", status=StepStatus.DONE, result=long_result),
            Step(id=2, task="search for events", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    
    current_step = plan.subtasks[1]
    context = _extract_search_context(plan, current_step)
    
    # Long result should not be folded in directly
    assert long_result not in context, "Long result should not be folded into context"


def test_extract_search_context_short_result_folded():
    """
    Unit test _extract_search_context folds in short prior results.
    """
    short_result = "The current year is 2026."  # Shorter than _SHORT_RESULT_CHAR_LIMIT (200)
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="determine year", tool_hint="none", status=StepStatus.DONE, result=short_result),
            Step(id=2, task="search for events", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    
    current_step = plan.subtasks[1]
    context = _extract_search_context(plan, current_step)
    
    assert short_result in context, "Short result should be folded into context"


def test_extract_search_context_no_prior_steps():
    """
    Unit test _extract_search_context returns empty string when no prior DONE steps exist.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search for events", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    
    current_step = plan.subtasks[0]
    context = _extract_search_context(plan, current_step)
    
    assert context == "", "Should return empty string when no prior DONE steps"


def test_relevance_check_irrelevant_fails():
    """
    Relevance check: irrelevant result → FAILED with a populated .error, not DONE.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search for specific fact", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_search_result = "Historical data from 1990, not relevant to current query"
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = mock_search_result
        
        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (False, "Result does not contain the specific information needed")
            
            result = tavily_search_node(state)
            
            assert result["plan"].subtasks[0].status == StepStatus.FAILED
            assert result["plan"].subtasks[0].error is not None
            assert "doesn't answer this step" in result["plan"].subtasks[0].error


def test_relevance_check_relevant_succeeds():
    """
    Relevance check: relevant result → DONE, .result set correctly.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search for specific fact", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_search_result = "The specific fact you need: 2026 World Cup winner is Argentina"
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = mock_search_result
        
        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")
            
            result = tavily_search_node(state)
            
            assert result["plan"].subtasks[0].status == StepStatus.DONE
            assert result["plan"].subtasks[0].result == mock_search_result
            assert result["plan"].subtasks[0].error is None


def test_search_exception_sets_failed():
    """
    Test that exception during search sets FAILED with error message.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search step", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.side_effect = Exception("Search API timeout")
        
        result = tavily_search_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert result["plan"].subtasks[0].error == "Search API timeout"


def test_tavily_search_node_none_plan_raises():
    """
    Test that tavily_search_node raises RuntimeError when called with no plan in state.
    """
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="tavily_search_node called with no plan"):
        tavily_search_node(state)


def test_tavily_search_node_no_running_step_raises():
    """
    Test that tavily_search_node raises RuntimeError when called with no RUNNING step.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with pytest.raises(RuntimeError, match="tavily_search_node called with no RUNNING step"):
        tavily_search_node(state)


def test_status_check_uses_basic_search_depth():
    """
    Test that status-check queries use "basic" search depth.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="check current status of tournament", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_search_result = "Status: ongoing"
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = mock_search_result
        
        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")
            
            tavily_search_node(state)
            
            # Verify search_depth parameter
            call_args = mock_tavily_search.call_args
            search_depth = call_args[1].get('search_depth')
            
            assert search_depth == "basic", "Status check should use basic search depth"


def test_non_status_check_uses_advanced_search_depth():
    """
    Test that non-status-check queries use "advanced" search depth.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search for detailed information", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_search_result = "Detailed information"
    
    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = mock_search_result
        
        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")
            
            tavily_search_node(state)
            
            # Verify search_depth parameter
            call_args = mock_tavily_search.call_args
            search_depth = call_args[1].get('search_depth')
            
            assert search_depth == "advanced", "Non-status check should use advanced search depth"
