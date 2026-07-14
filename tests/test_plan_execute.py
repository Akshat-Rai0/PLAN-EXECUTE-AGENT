import pytest
from typing import TypedDict, Optional
from src.agents.plan_execute.graph import build_graph
from src.agents.plan_execute.state import State, Plan

# Test cases - add more inputs here to test different scenarios
TEST_INPUTS = [
    "Plan a weekend trip to Goa",
    "Write a hello world program",
    "Create a simple REST API",
    "Build a todo list application",
    "Learn Python basics"
]


def test_state_structure():
    """Test that State has the required fields."""
    from src.agents.plan_execute.state import Step, StepStatus
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="test task", status=StepStatus.PENDING)
        ]
    )
    
    state: State = {
        "input": "test input",
        "plan": plan,
        "output": "test output"
    }
    
    assert state["input"] == "test input"
    assert state["plan"].goal == "test goal"
    assert state["output"] == "test output"


def test_state_with_none_plan():
    """Test State with None plan."""
    state: State = {
        "input": "test input",
        "plan": None,
        "output": ""
    }
    
    assert state["input"] == "test input"
    assert state["plan"] is None
    assert state["output"] == ""


def test_state_types():
    """Test that State fields have correct types."""
    from src.agents.plan_execute.state import Step, StepStatus
    
    plan = Plan(
        goal="Write a hello world program",
        subtasks=[
            Step(id=1, task="Step 1", status=StepStatus.PENDING),
            Step(id=2, task="Step 2", status=StepStatus.PENDING)
        ]
    )
    
    state: State = {
        "input": "Write a hello world program",
        "plan": plan,
        "output": "Step 1 → Step 2 → Step 3"
    }
    
    assert isinstance(state["input"], str)
    assert isinstance(state["plan"], Plan) or state["plan"] is None
    assert isinstance(state["output"], str)


@pytest.mark.parametrize("input_task", TEST_INPUTS)
def test_plan_generation(input_task):
    """Test plan generation for various input tasks."""
    graph = build_graph()
    
    initial_state: State = {
        "input": input_task,
        "plan": None,
        "output": ""
    }
    
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify plan was generated
    assert result["plan"] is not None
    assert isinstance(result["plan"], Plan)
    
    # Verify output was generated
    assert result["output"] is not None
    assert isinstance(result["output"], str)
    assert len(result["output"]) > 0
    
    # Validate Plan structure
    plan = result["plan"]
    assert plan.goal == input_task
    assert len(plan.subtasks) > 0
    
    # Validate subtask structure
    for subtask in plan.subtasks:
        assert subtask.id is not None
        assert subtask.task is not None
        assert subtask.tool_hint is not None
        assert subtask.status.value in ["PENDING", "RUNNING", "DONE", "FAILED"]
        assert isinstance(subtask.sensitive, bool)
    
    print(f"\nInput: {input_task}")
    print(f"Plan: {plan.model_dump_json(indent=2)}")


def test_goa_trip_specific():
    """Specific test for Goa trip planning."""
    graph = build_graph()
    
    initial_state: State = {
        "input": "Plan a weekend trip to Goa",
        "plan": None,
        "output": ""
    }
    
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(initial_state, config)
    
    assert result["plan"] is not None
    assert isinstance(result["plan"], Plan)
    
    # Validate Plan structure
    plan = result["plan"]
    assert plan.goal == "Plan a weekend trip to Goa"
    assert len(plan.subtasks) > 0
    
    # Validate subtask structure
    for subtask in plan.subtasks:
        assert subtask.id is not None
        assert subtask.task is not None
        assert subtask.tool_hint is not None
        assert subtask.status.value == "PENDING"  # Should be PENDING initially
        assert isinstance(subtask.sensitive, bool)
    
    print(f"\nGoa Trip Plan: {plan.model_dump_json(indent=2)}")
