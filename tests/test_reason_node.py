"""Regression tests for reason_node execution and context handling."""

import pytest
from src.agents.plan_execute.nodes import reason_node
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def test_reason_node_produces_real_result():
    """
    Regression test for silent-stub bug.
    reason_node should produce a real result, not the old [stub] placeholder.
    Mock the LLM, assert step.result equals the mocked response, step.status == DONE.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="determine current date", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "The current date is 2026-07-16"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = reason_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert result["plan"].subtasks[0].result == "The current date is 2026-07-16"
        assert "[stub]" not in result["plan"].subtasks[0].result


def test_prior_context_included_in_prompt():
    """
    Regression test for context inclusion bug.
    Prior DONE step context should actually be included in the prompt.
    Mock the LLM to capture what prompt it was called with, assert an earlier step's result text appears in it.
    """
    plan = Plan(
        goal="Plan a weekend trip to Goa",
        subtasks=[
            Step(id=1, task="search for Goa weather", tool_hint="web_search", status=StepStatus.DONE, result="Goa weather: Sunny, 32°C"),
            Step(id=2, task="plan itinerary based on weather", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Based on sunny weather, plan beach activities"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        reason_node(state)
        
        # Capture the prompt that was sent to the LLM
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        assert "Goa weather: Sunny, 32°C" in prompt_content, "Prior step result should be included in prompt"
        assert "Step 1: search for Goa weather" in prompt_content, "Prior step task should be included in prompt"


def test_llm_exception_sets_failed():
    """
    Test that exception during LLM call sets FAILED with the error message, not an unhandled crash.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="reasoning step", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM API error")
        mock_get_llm.return_value = mock_llm
        
        result = reason_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert result["plan"].subtasks[0].error == "LLM API error"


def test_reason_node_with_no_prior_steps():
    """
    Test reason_node when there are no prior DONE steps (first step in plan).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="determine current date", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "The current date is 2026-07-16"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = reason_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert result["plan"].subtasks[0].result == "The current date is 2026-07-16"


def test_reason_node_long_prior_result_truncated():
    """
    Test that long prior results are truncated before being included in the prompt.
    """
    long_result = "A" * 2000  # Create a result longer than 1500 chars
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="long search result", tool_hint="web_search", status=StepStatus.DONE, result=long_result),
            Step(id=2, task="reasoning step", tool_hint="none", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Reasoning result"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        reason_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # Should contain truncation marker
        assert "... [truncated]" in prompt_content, "Long results should be truncated"
        # Should not contain the full 2000 chars
        assert len(prompt_content) < 2500, "Prompt should be truncated to reasonable length"


def test_reason_node_none_plan_raises():
    """
    Test that reason_node raises RuntimeError when called with no plan in state.
    """
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="reason_node called with no plan"):
        reason_node(state)


def test_reason_node_no_running_step_raises():
    """
    Test that reason_node raises RuntimeError when called with no RUNNING step.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with pytest.raises(RuntimeError, match="reason_node called with no RUNNING step"):
        reason_node(state)
