"""Tests for Tavily search API usage through the graph flow."""

import pytest
from src.agents.plan_execute.graph import build_graph
from src.agents.plan_execute.state import State


def test_tavily_search_fifa_world_cup_through_graph():
    """Test Tavily search with FIFA World Cup query through the full graph flow."""
    query = "Who won the most recent FIFA World Cup match and highlight important moments"
    
    graph = build_graph().compile()
    
    initial_state: State = {
        "input": query,
        "plan": None
    }
    
    config = {"configurable": {"thread_id": "test-fifa-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify plan was generated
    assert result["plan"] is not None
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"{'='*80}")
    print(f"\nGenerated Plan:")
    print(f"Goal: {result['plan'].goal}")
    print(f"\nSteps:")
    
    # Print all steps and their results
    for step in result["plan"].subtasks:
        print(f"\n  Step {step.id}: {step.task}")
        print(f"  Tool Hint: {step.tool_hint}")
        print(f"  Status: {step.status}")
        if step.result:
            print(f"  Result: {step.result}")
        if step.error:
            print(f"  Error: {step.error}")
    
    # Verify at least one step used web_search
    search_steps = [s for s in result["plan"].subtasks if s.tool_hint in ["web_search", "tavily_search"]]
    assert len(search_steps) > 0, "Plan should include at least one web_search step"
    
    # Verify search steps were executed
    executed_search_steps = [s for s in search_steps if s.status.value in ["DONE", "RUNNING"]]
    assert len(executed_search_steps) > 0, "At least one search step should be executed"
    
    # Verify results contain FIFA/World Cup information
    all_results = " ".join([s.result for s in result["plan"].subtasks if s.result])
    assert "FIFA" in all_results or "World Cup" in all_results or "world cup" in all_results.lower()
    
    print(f"\n{'='*80}")
    print(f"{'='*80}")


def test_tavily_search_basic_through_graph():
    """Test basic Tavily search functionality through the graph flow."""
    query = "What is the capital of France?"
    
    graph = build_graph().compile()
    
    initial_state: State = {
        "input": query,
        "plan": None
    }
    
    config = {"configurable": {"thread_id": "test-basic-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify plan was generated
    assert result["plan"] is not None
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"{'='*80}")
    print(f"\nGenerated Plan:")
    print(f"Goal: {result['plan'].goal}")
    print(f"\nSteps:")
    
    # Print all steps and their results
    for step in result["plan"].subtasks:
        print(f"\n  Step {step.id}: {step.task}")
        print(f"  Tool Hint: {step.tool_hint}")
        print(f"  Status: {step.status}")
        if step.result:
            print(f"  Result: {step.result}")
        if step.error:
            print(f"  Error: {step.error}")
    
    print(f"\n{'='*80}")
    print(f"{'='*80}")


def test_tavily_search_complex_query_through_graph():
    """Test Tavily search with complex multi-part query through the graph flow."""
    query = "Latest developments in artificial intelligence and machine learning in 2024"
    
    graph = build_graph().compile()
    
    initial_state: State = {
        "input": query,
        "plan": None
    }
    
    config = {"configurable": {"thread_id": "test-complex-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify plan was generated
    assert result["plan"] is not None
    print(f"\n{'='*80}")
    print(f"Query: {query}")
    print(f"{'='*80}")
    print(f"\nGenerated Plan:")
    print(f"Goal: {result['plan'].goal}")
    print(f"\nSteps:")
    
    # Print all steps and their results
    for step in result["plan"].subtasks:
        print(f"\n  Step {step.id}: {step.task}")
        print(f"  Tool Hint: {step.tool_hint}")
        print(f"  Status: {step.status}")
        if step.result:
            print(f"  Result: {step.result}")
        if step.error:
            print(f"  Error: {step.error}")
    
    # Verify results contain relevant keywords
    all_results = " ".join([s.result for s in result["plan"].subtasks if s.result])
    result_lower = all_results.lower()
    assert any(keyword in result_lower for keyword in ["artificial intelligence", "ai", "machine learning", "ml"])
    
    print(f"\n{'='*80}")
    print(f"{'='*80}")
