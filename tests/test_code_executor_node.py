"""Tests for code_executor_node execution and error handling."""

import pytest
from src.agents.plan_execute.nodes import code_executor_node, _is_fixable_error
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from unittest.mock import patch, MagicMock
from src.sandbox.models import SandboxResult


def test_code_executor_node_produces_real_result():
    """
    Test that code_executor_node produces a real result from sandbox execution.
    Mock both LLM and sandbox to verify the flow.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="calculate 2 + 2", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_llm_response = MagicMock()
    mock_llm_response.content = "print(2 + 2)"
    
    mock_sandbox_result = SandboxResult(
        success=True,
        stdout="4",
        stderr="",
        exit_code=0,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm
        mock_run_sandbox.return_value = mock_sandbox_result
        
        result = code_executor_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert result["plan"].subtasks[0].result == "4"
        assert "[stub]" not in result["plan"].subtasks[0].result


def test_code_executor_node_with_fixable_error_auto_retry():
    """
    Test that fixable errors trigger auto-retry with error context.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="use math module", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    # First attempt: missing import
    first_llm_response = MagicMock()
    first_llm_response.content = "print(math.sqrt(4))"
    
    first_sandbox_result = SandboxResult(
        success=False,
        stdout="",
        stderr="NameError: name 'math' is not defined",
        error="NameError: name 'math' is not defined",
        exit_code=1,
        duration_seconds=0.1
    )
    
    # Second attempt: fixed with import
    second_llm_response = MagicMock()
    second_llm_response.content = "import math\nprint(math.sqrt(4))"
    
    second_sandbox_result = SandboxResult(
        success=True,
        stdout="2.0",
        stderr="",
        exit_code=0,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = [first_llm_response, second_llm_response]
        mock_get_llm.return_value = mock_llm
        mock_run_sandbox.side_effect = [first_sandbox_result, second_sandbox_result]
        
        result = code_executor_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert result["plan"].subtasks[0].result == "2.0"
        assert mock_llm.invoke.call_count == 2  # Should have retried


def test_code_executor_node_with_logical_error_no_retry():
    """
    Test that logical errors (ValueError, etc.) do not trigger auto-retry.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="calculate square root of negative number", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_llm_response = MagicMock()
    mock_llm_response.content = "import math\nprint(math.sqrt(-1))"
    
    mock_sandbox_result = SandboxResult(
        success=False,
        stdout="",
        stderr="ValueError: math domain error",
        error="ValueError: math domain error",
        exit_code=1,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm
        mock_run_sandbox.return_value = mock_sandbox_result
        
        result = code_executor_node(state)
        
        # Unfixable errors mark the step FAILED (not DONE) so
        # _route_after_tool sends it to the replanner instead of letting a
        # buried error message masquerade as a completed result.
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert "Code execution failed" in result["plan"].subtasks[0].result
        assert "ValueError" in result["plan"].subtasks[0].result
        assert mock_llm.invoke.call_count == 1  # Should NOT have retried


def test_code_executor_node_prior_context_included():
    """
    Test that prior DONE step results are included in the code generation prompt.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="calculate 2 + 2", tool_hint="code_executor", status=StepStatus.DONE, result="4"),
            Step(id=2, task="add 3 to previous result", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    mock_llm_response = MagicMock()
    mock_llm_response.content = "print(4 + 3)"
    
    mock_sandbox_result = SandboxResult(
        success=True,
        stdout="7",
        stderr="",
        exit_code=0,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm
        mock_run_sandbox.return_value = mock_sandbox_result
        
        code_executor_node(state)
        
        # Capture the prompt
        call_args = mock_llm.invoke.call_args
        messages = call_args[0][0]
        human_message = messages[1]
        prompt_content = human_message.content
        
        assert "4" in prompt_content, "Prior step result should be included in prompt"
        assert "Step 1: calculate 2 + 2" in prompt_content, "Prior step task should be included in prompt"


def test_code_executor_node_removes_markdown_fences():
    """
    Test that markdown code fences are removed from LLM response before execution.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="print hello", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    # LLM returns code with markdown fences
    mock_llm_response = MagicMock()
    mock_llm_response.content = '```python\nprint("hello")\n```'
    
    mock_sandbox_result = SandboxResult(
        success=True,
        stdout="hello",
        stderr="",
        exit_code=0,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm
        
        # Capture what code was actually passed to sandbox
        def capture_code(code, *args, **kwargs):
            assert '```' not in code, "Markdown fences should be removed"
            assert code == 'print("hello")', "Code should be clean"
            return mock_sandbox_result
        
        mock_run_sandbox.side_effect = capture_code
        
        result = code_executor_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert result["plan"].subtasks[0].result == "hello"


def test_is_fixable_error():
    """
    Test the _is_fixable_error helper function.
    """
    assert _is_fixable_error("ImportError: No module named 'xyz'") is True
    assert _is_fixable_error("ModuleNotFoundError: No module named 'xyz'") is True
    assert _is_fixable_error("IndexError: list index out of range") is True
    assert _is_fixable_error("KeyError: 'missing_key'") is True
    assert _is_fixable_error("AttributeError: 'NoneType' object has no attribute 'x'") is True
    assert _is_fixable_error("TypeError: unsupported operand type(s)") is True
    assert _is_fixable_error("NameError: name 'undefined' is not defined") is True
    
    # Logical errors should not be fixable
    assert _is_fixable_error("ValueError: invalid literal for int()") is False
    assert _is_fixable_error("AssertionError: test failed") is False
    assert _is_fixable_error("RuntimeError: something went wrong") is False


def test_code_executor_node_none_plan_raises():
    """
    Test that code_executor_node raises RuntimeError when called with no plan in state.
    """
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="code_executor_node called with no plan"):
        code_executor_node(state)


def test_code_executor_node_no_running_step_raises():
    """
    Test that code_executor_node raises RuntimeError when called with no RUNNING step.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="code_executor", status=StepStatus.DONE)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with pytest.raises(RuntimeError, match="code_executor_node called with no RUNNING step"):
        code_executor_node(state)


def test_code_executor_node_max_retries_exceeded():
    """
    Test that after max retries (2), the node gives up and returns the error.
    """
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="use undefined module", tool_hint="code_executor", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    # All attempts fail with the same fixable error
    mock_llm_response = MagicMock()
    mock_llm_response.content = "print(undefined_module.func())"
    
    mock_sandbox_result = SandboxResult(
        success=False,
        stdout="",
        stderr="NameError: name 'undefined_module' is not defined",
        error="NameError: name 'undefined_module' is not defined",
        exit_code=1,
        duration_seconds=0.1
    )
    
    with patch('src.agents.plan_execute.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.plan_execute.nodes.run_in_sandbox') as mock_run_sandbox:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_llm_response
        mock_get_llm.return_value = mock_llm
        mock_run_sandbox.return_value = mock_sandbox_result
        
        result = code_executor_node(state)
        
        # Retries exhausted with no success marks the step FAILED (not DONE)
        # so the replanner engages instead of a buried error being read as
        # a legitimate result.
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert "Code execution failed" in result["plan"].subtasks[0].result
        assert "NameError" in result["plan"].subtasks[0].result
        assert mock_llm.invoke.call_count == 3  # Initial + 2 retries
