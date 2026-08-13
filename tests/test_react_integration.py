"""Integration tests for React arm (ReAct baseline agent)."""

import pytest
from src.agents.react.nodes import react_step, _detect_repeat_loop, _truncate, _render_history, _strip_wrapping_quotes
from src.agents.react.state import Turn, ReactState
from unittest.mock import patch, MagicMock


def test_truncate_at_limit():
    """Test that _truncate doesn't truncate when value is under limit."""
    value = "short text"
    result = _truncate(value, limit=100)
    assert result == value


def test_truncate_exceeds_limit():
    """Test that _truncate truncates when value exceeds limit."""
    value = "a" * 200
    result = _truncate(value, limit=100)
    assert len(result) < len(value)
    assert "truncated" in result


def test_truncate_at_exact_limit():
    """Test that _truncate handles exact limit boundary."""
    value = "a" * 100
    result = _truncate(value, limit=100)
    assert result == value


def test_detect_repeat_loop_below_threshold():
    """Test that _detect_repeat_loop returns empty string when below threshold."""
    history = [
        Turn(thought="test", action="web_search", action_input="query", observation="result")
    ]
    result = _detect_repeat_loop(history, threshold=3)
    assert result == ""


def test_detect_repeat_loop_at_threshold():
    """Test that _detect_repeat_loop detects loop at threshold."""
    history = [
        Turn(thought="test", action="web_search", action_input="query", observation="ERROR: failed")
        for _ in range(3)
    ]
    result = _detect_repeat_loop(history, threshold=3)
    assert "LOOP WARNING" in result
    assert "web_search" in result


def test_detect_repeat_loop_different_actions():
    """Test that _detect_repeat_loop doesn't trigger on different actions."""
    history = [
        Turn(thought="test", action=f"action_{i}", action_input="query", observation="ERROR: failed")
        for i in range(3)
    ]
    result = _detect_repeat_loop(history, threshold=3)
    assert result == ""


def test_detect_repeat_loop_no_errors():
    """Test that _detect_repeat_loop doesn't trigger without errors."""
    history = [
        Turn(thought="test", action="web_search", action_input="query", observation="success")
        for _ in range(3)
    ]
    result = _detect_repeat_loop(history, threshold=3)
    assert result == ""


def test_render_history_empty():
    """Test that _render_history handles empty history."""
    result = _render_history([])
    assert result == ""


def test_render_history_single_turn():
    """Test that _render_history handles single turn."""
    history = [
        Turn(thought="test thought", action="web_search", action_input="query", observation="result")
    ]
    result = _render_history(history)
    assert "Thought: test thought" in result
    assert "Action: web_search" in result
    assert "Observation: result" in result


def test_render_history_truncation():
    """Test that _render_history truncates long history."""
    history = [
        Turn(
            thought="a" * 2000,
            action="web_search",
            action_input="b" * 2000,
            observation="c" * 2000
        )
        for _ in range(10)
    ]
    result = _render_history(history)
    assert len(result) < 10000  # Should be truncated
    assert "truncated" in result or "omitted" in result


def test_render_history_omits_old_turns():
    """Test that _render_history omits old turns when over limit."""
    history = [
        Turn(thought=f"thought {i}", action="web_search", action_input="query", observation="result")
        for i in range(10)
    ]
    result = _render_history(history)
    assert "omitted" in result


def test_strip_wrapping_quotes_double():
    """Test that _strip_wrapping_quotes removes double quotes."""
    result = _strip_wrapping_quotes('"test"')
    assert result == "test"


def test_strip_wrapping_quotes_single():
    """Test that _strip_wrapping_quotes removes single quotes."""
    result = _strip_wrapping_quotes("'test'")
    assert result == "test"


def test_strip_wrapping_quotes_no_quotes():
    """Test that _strip_wrapping_quotes doesn't remove when no quotes."""
    result = _strip_wrapping_quotes("test")
    assert result == "test"


def test_strip_wrapping_quotes_mismatched():
    """Test that _strip_wrapping_quotes doesn't remove mismatched quotes."""
    result = _strip_wrapping_quotes('"test\'')
    assert result == '"test\''


def test_strip_wrapping_quotes_nested():
    """Test that _strip_wrapping_quotes only removes outer layer."""
    result = _strip_wrapping_quotes('"test \'nested\'"')
    assert result == "test 'nested'"


def test_strip_wrapping_quotes_json():
    """Test that _strip_wrapping_quotes doesn't strip JSON."""
    result = _strip_wrapping_quotes('{"key": "value"}')
    assert result == '{"key": "value"}'


def test_react_step_with_final_answer():
    """Test react_step with final_answer action."""
    state: ReactState = {
        "goal": "test goal",
        "history": []
    }
    
    mock_response = MagicMock()
    mock_response.content = "Thought: done\nAction: final_answer\nAction Input: the answer"
    
    with patch('src.agents.react.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = react_step(state)
        
        assert result["final_answer"] == "the answer"
        assert result["iterations"] == 1


def test_react_step_with_parse_error():
    """Test react_step handles parse errors gracefully."""
    state: ReactState = {
        "goal": "test goal",
        "history": []
    }
    
    mock_response = MagicMock()
    mock_response.content = "invalid response without proper format"
    
    with patch('src.agents.react.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = react_step(state)
        
        assert "history" in result
        assert len(result["history"]) == 1
        assert result["history"][0].action == "error"


def test_react_step_with_web_search():
    """Test react_step with web_search action."""
    state: ReactState = {
        "goal": "test goal",
        "history": []
    }
    
    mock_response = MagicMock()
    mock_response.content = "Thought: need info\nAction: web_search\nAction Input: test query"
    
    with patch('src.agents.react.nodes.get_llm') as mock_get_llm, \
         patch('src.agents.react.nodes.tavily_search') as mock_search:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        mock_search.return_value = "search results"
        
        result = react_step(state)
        
        assert "history" in result
        assert len(result["history"]) == 1
        assert result["history"][0].action == "web_search"
        assert result["history"][0].observation == "search results"


def test_react_step_with_shell_command_without_workspace():
    """Test react_step with shell_command when workspace not set."""
    state: ReactState = {
        "goal": "test goal",
        "history": []
    }
    
    mock_response = MagicMock()
    mock_response.content = "Thought: run command\nAction: shell_command\nAction Input: ls"
    
    with patch('src.agents.react.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = react_step(state)
        
        assert "history" in result
        assert "ERROR: workspace_path not set" in result["history"][0].observation


def test_react_step_with_unknown_action():
    """Test react_step handles unknown actions."""
    state: ReactState = {
        "goal": "test goal",
        "history": []
    }
    
    mock_response = MagicMock()
    mock_response.content = "Thought: try something\nAction: unknown_action\nAction Input: test"
    
    with patch('src.agents.react.nodes.get_llm') as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm
        
        result = react_step(state)
        
        assert "history" in result
        assert "Unknown action" in result["history"][0].observation
