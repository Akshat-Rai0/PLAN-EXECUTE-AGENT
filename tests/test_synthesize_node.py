"""Regression tests for synthesize_node final answer generation."""

import pytest
from src.agents.plan_execute.nodes import synthesize_node
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock


def test_writes_to_plan_final_answer():
    """
    Direct regression test for the original silent-discard bug.
    synthesize_node should write to plan.final_answer, not a tool_hint == "none" step.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.DONE, result="Result 2"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final synthesized answer based on results"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = synthesize_node(state)
        
        assert result["plan"].final_answer == "Final synthesized answer based on results"
        assert result["plan"].final_answer is not None


def test_no_results_graceful_fallback():
    """
    No step results at all → graceful fallback message, not a crash.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.PENDING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    result = synthesize_node(state)
    
    assert result["plan"].final_answer == "No step results were available to synthesize a final answer."
    assert result["plan"].final_answer is not None


def test_long_results_truncated():
    """
    Long step results get truncated before going into the prompt (the 1500-char truncation).
    Cheap sanity check.
    """
    long_result = "A" * 2000  # Longer than 1500 chars
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result=long_result),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        synthesize_node(state)
        
        # Capture the prompt that was sent to the LLM
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # Should contain truncation marker
        assert "... [truncated]" in prompt_content, "Long results should be truncated in prompt"
        # Should not contain the full 2000 chars
        assert len(prompt_content) < 2500, "Prompt should be truncated to reasonable length"


def test_synthesize_includes_all_step_results():
    """
    Test that synthesize_node includes results from all DONE steps.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.DONE, result="Result 2"),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.DONE, result="Result 3"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        synthesize_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # All step results should be included
        assert "Result 1" in prompt_content
        assert "Result 2" in prompt_content
        assert "Result 3" in prompt_content


def test_synthesize_includes_step_errors():
    """
    Test that synthesize_node includes error messages from FAILED steps.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="API timeout"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        synthesize_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # Error should be included
        assert "API timeout" in prompt_content
        assert "Error:" in prompt_content


def test_synthesize_none_plan_raises():
    """
    Test that synthesize_node raises RuntimeError when called with no plan in state.
    """
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="synthesize_node called with no plan"):
        synthesize_node(state)


def test_synthesize_with_mixed_results_and_errors():
    """
    Test synthesize_node with a mix of DONE results and FAILED errors.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.FAILED, error="Error 2"),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.DONE, result="Result 3"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final synthesized answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = synthesize_node(state)
        
        assert result["plan"].final_answer == "Final synthesized answer"


def test_synthesize_includes_goal_in_prompt():
    """
    Test that the original goal is included in the synthesis prompt.
    """
    plan = Plan(
        goal="Plan a weekend trip to Goa",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        synthesize_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # Goal should be in the prompt
        assert "Plan a weekend trip to Goa" in prompt_content


def test_synthesize_ignores_pending_steps():
    """
    Test that synthesize_node ignores PENDING steps (only includes DONE/FAILED).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
            Step(id=2, task="step 2", tool_hint="web_search", status=StepStatus.PENDING),
            Step(id=3, task="step 3", tool_hint="web_search", status=StepStatus.DONE, result="Result 3"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_response = MagicMock()
    mock_response.content = "Final answer"
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        synthesize_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        # Only DONE steps should be included
        assert "Result 1" in prompt_content
        assert "Result 3" in prompt_content
        # PENDING step should not be mentioned
        assert "step 2" not in prompt_content or "PENDING" not in prompt_content


def test_synthesize_llm_exception_propagates():
    """
    Test that LLM exceptions during synthesis are not caught (should propagate).
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="web_search", status=StepStatus.DONE, result="Result 1"),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM synthesis error")
        mock_get_llm.return_value = mock_llm
        
        with pytest.raises(Exception, match="LLM synthesis error"):
            synthesize_node(state)
