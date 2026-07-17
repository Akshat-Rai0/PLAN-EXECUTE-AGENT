"""
Regression tests for Tavily search parameter tuning.

Context: paired comparisons against the ReAct baseline (F1 "last race" and
FIFA World Cup 2026 "latest match") showed the same root cause behind two
distinct failures — general web search surfaced well-indexed
historical/reference content (a "F1 winners" page still listing a 2025 race,
Wikipedia-style World Cup pages) that passed relevance checks and a raw
days=7 filter, even though the SPECIFIC fact needed was stale.

Fix: tavily_search now accepts a `recency_sensitive` flag. When True, it
uses Tavily's topic="news" + time_range="week" instead of the default
topic="general" + days=7 — topic="news" applies much stronger recency
weighting, since a raw day-count filter doesn't reliably exclude reference
pages whose last-modified timestamp is recent even when their content spans
years.

tavily_search_node wires this flag from the SAME recency-keyword detection
already used for the deterministic date-anchor feature (_needs_date_anchor),
checked against both the overall goal and the individual step's task text.
"""

import pytest
from unittest.mock import patch, MagicMock


# --- tavily_search itself (src/tools/registry.py) -------------------------

def test_recency_sensitive_uses_news_topic_and_time_range():
    """
    recency_sensitive=True should call the Tavily client with
    topic="news" and time_range="week", NOT the default days=7.
    """
    from src.tools.registry import tavily_search

    mock_client = MagicMock()
    mock_client.search.return_value = {"results": [{"content": "some result"}]}

    with patch('src.tools.registry.client', mock_client):
        tavily_search("latest F1 race winner", recency_sensitive=True)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("topic") == "news"
        assert call_kwargs.get("time_range") == "week"
        assert "days" not in call_kwargs, \
            "recency_sensitive search should not also pass the old days= filter"


def test_non_recency_sensitive_uses_default_days_filter():
    """
    recency_sensitive=False (default) should preserve the original
    behavior — days=7, no topic/time_range override.
    """
    from src.tools.registry import tavily_search

    mock_client = MagicMock()
    mock_client.search.return_value = {"results": [{"content": "some result"}]}

    with patch('src.tools.registry.client', mock_client):
        tavily_search("explain photosynthesis")

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("days") == 7
        assert "topic" not in call_kwargs
        assert "time_range" not in call_kwargs


def test_recency_sensitive_preserves_other_params():
    """
    Adding recency_sensitive handling should not drop the existing
    search_depth, max_results, chunks_per_source, etc. params.
    """
    from src.tools.registry import tavily_search

    mock_client = MagicMock()
    mock_client.search.return_value = {"results": [{"content": "some result"}]}

    with patch('src.tools.registry.client', mock_client):
        tavily_search("query", search_depth="advanced", recency_sensitive=True)

        call_kwargs = mock_client.search.call_args.kwargs
        assert call_kwargs.get("search_depth") == "advanced"
        assert call_kwargs.get("max_results") == 3
        assert call_kwargs.get("chunks_per_source") == 3
        assert call_kwargs.get("include_answer") is False
        assert call_kwargs.get("include_raw_content") is False


# --- tavily_search_node wiring (src/agents/plan_execute/nodes.py) --------

def test_tavily_search_node_passes_recency_sensitive_for_recency_goal():
    """
    When the overall goal contains recency language, tavily_search_node
    should call tavily_search with recency_sensitive=True, even if the
    individual step's own task text doesn't repeat that language.
    """
    from src.agents.plan_execute.nodes import tavily_search_node
    from src.agents.plan_execute.state import State, Plan, Step, StepStatus

    plan = Plan(
        goal="who won the most recent FIFA World Cup 2026 match",
        subtasks=[
            Step(id=1, task="find the match schedule", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}

    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = "some result"

        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")

            tavily_search_node(state)

            call_kwargs = mock_tavily_search.call_args.kwargs
            assert call_kwargs.get("recency_sensitive") is True


def test_tavily_search_node_passes_recency_sensitive_for_recency_step_task():
    """
    Even if the overall goal has no recency language, an individual step
    whose OWN task text does (e.g. a replanned, narrowed follow-up step)
    should still trigger recency_sensitive=True.
    """
    from src.agents.plan_execute.nodes import tavily_search_node
    from src.agents.plan_execute.state import State, Plan, Step, StepStatus

    plan = Plan(
        goal="research Formula 1",
        subtasks=[
            Step(id=1, task="find the latest race result", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}

    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = "some result"

        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")

            tavily_search_node(state)

            call_kwargs = mock_tavily_search.call_args.kwargs
            assert call_kwargs.get("recency_sensitive") is True


def test_tavily_search_node_no_recency_sensitive_for_static_goal():
    """
    A goal and step with no recency language at all should call
    tavily_search with recency_sensitive=False.
    """
    from src.agents.plan_execute.nodes import tavily_search_node
    from src.agents.plan_execute.state import State, Plan, Step, StepStatus

    plan = Plan(
        goal="explain how photosynthesis works",
        subtasks=[
            Step(id=1, task="search for a definition of photosynthesis", tool_hint="web_search", status=StepStatus.RUNNING)
        ]
    )
    state: State = {"input": "test", "plan": plan}

    with patch('src.agents.plan_execute.nodes.tavily_search') as mock_tavily_search:
        mock_tavily_search.return_value = "some result"

        with patch('src.agents.plan_execute.nodes._check_search_relevance') as mock_relevance:
            mock_relevance.return_value = (True, "Relevant")

            tavily_search_node(state)

            call_kwargs = mock_tavily_search.call_args.kwargs
            assert call_kwargs.get("recency_sensitive") is False
