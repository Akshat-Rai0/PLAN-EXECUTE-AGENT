import pytest
from unittest.mock import patch, MagicMock
from langchain_core.messages import AIMessage

from src.agents.plan_execute.nodes import (
    preprocess_search_query,
    search_query_preprocessor_node,
    tavily_search_node,
)
from src.agents.plan_execute.state import State, Plan, Step, StepStatus


def test_preprocess_search_query_with_llm():
    """Test that LLM reformulates an ambiguous step task into an exact query."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="James Webb Space Telescope launch date")

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm):
        result = preprocess_search_query(
            goal="When was the James Webb Space Telescope launched?",
            step_task="Step 1: Search for when it was launched",
            prior_context="James Webb Space Telescope",
            current_date="2026-08-19",
        )

        assert result == "James Webb Space Telescope launch date"
        assert mock_llm.invoke.called


def test_preprocess_search_query_strips_quotes_and_prefixes():
    """Test that formatting artifacts like 'Query: ...' or quotes are cleanly stripped."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content='Query: "Paris 2024 Olympics men 100m winner"')

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm):
        result = preprocess_search_query(
            goal="Who won the 100m in Paris 2024?",
            step_task="Find out who won it",
        )

        assert result == "Paris 2024 Olympics men 100m winner"


def test_preprocess_search_query_fallback_on_llm_failure():
    """Test heuristic fallback if the LLM fails."""
    mock_llm = MagicMock()
    mock_llm.invoke.side_effect = RuntimeError("LLM API timeout")

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm):
        result = preprocess_search_query(
            goal="Tokyo Population",
            step_task="Step 1: Search online for current population of Tokyo",
            prior_context="2026",
        )

        assert "Tokyo Population" in result
        assert "population of Tokyo" in result
        assert "Step 1:" not in result


def test_preprocess_search_query_length_cap():
    """Test that queries exceeding 400 characters are capped cleanly."""
    long_task = "a" * 500
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="b" * 500)

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm):
        result = preprocess_search_query(goal="Test", step_task=long_task)
        assert len(result) <= 400


def test_tavily_search_node_uses_preprocessed_query():
    """Test that tavily_search_node calls tavily_search with the preprocessed query."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="exact rewritten search query")

    step = Step(
        id=1,
        task="Find out details about it",
        tool_hint="web_search",
        status=StepStatus.RUNNING,
    )
    plan = Plan(goal="Quantum Computing Breakthroughs 2026", subtasks=[step])
    state: State = {
        "input": "Quantum Computing",
        "plan": plan,
        "replan_count": 0,
        "steps_executed": 0,
        "consecutive_identical_replans": 0,
        "last_replan_context": None,
        "workspace_path": None,
        "server_url": None,
        "pending_approval": None,
        "approval_events": [],
        "human_questions": [],
    }

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm), \
         patch("src.agents.plan_execute.nodes.tavily_search", return_value="Search result contents") as mock_tavily, \
         patch("src.agents.plan_execute.nodes._search_relevance_validation_enabled", return_value=False):
        
        result_state = tavily_search_node(state)
        
        mock_tavily.assert_called_once()
        args, kwargs = mock_tavily.call_args
        assert args[0] == "exact rewritten search query"
        assert step.status == StepStatus.DONE
        assert step.result == "Search result contents"


def test_search_query_preprocessor_node():
    """Test standalone search_query_preprocessor_node execution."""
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = AIMessage(content="rewritten query")

    step = Step(
        id=1,
        task="Search for something",
        tool_hint="web_search",
        status=StepStatus.RUNNING,
    )
    plan = Plan(goal="Test Goal", subtasks=[step])
    state: State = {
        "input": "Test Goal",
        "plan": plan,
        "replan_count": 0,
        "steps_executed": 0,
        "consecutive_identical_replans": 0,
        "last_replan_context": None,
        "workspace_path": None,
        "server_url": None,
        "pending_approval": None,
        "approval_events": [],
        "human_questions": [],
    }

    with patch("src.agents.plan_execute.nodes.get_cheap_llm", return_value=mock_llm):
        out = search_query_preprocessor_node(state)
        assert out["plan"] is plan
