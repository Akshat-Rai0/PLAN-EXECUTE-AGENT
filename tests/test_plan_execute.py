"""Tests for plan execution agent with Pydantic models."""

import pytest
from src.agents.plan_execute.graph import build_graph
from src.agents.plan_execute.state import State, Plan, Step, StepStatus


# Test cases - add more inputs here to test different scenarios
TEST_INPUTS = [
    "Plan a weekend trip to Goa",
    "Write a hello world program",
    "Create a simple REST API",
    "Build a todo list application",
    "Learn Python basics"
]


def test_state_structure():
    """Test that State has the required fields with Plan model."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="test task", status=StepStatus.PENDING)
        ]
    )
    
    state: State = {
        "input": "test input",
        "plan": plan
    }
    
    assert state["input"] == "test input"
    assert state["plan"].goal == "test goal"


def test_state_with_none_plan():
    """Test State with None plan."""
    state: State = {
        "input": "test input",
        "plan": None
    }
    
    assert state["input"] == "test input"
    assert state["plan"] is None


def test_step_model_validation():
    """Test Step model validation with all fields."""
    step = Step(
        id=1,
        task="Test task",
        tool_hint="web_search",
        status=StepStatus.PENDING,
        sensitive=True,
        result="Test result",
        error=None
    )
    
    assert step.id == 1
    assert step.task == "Test task"
    assert step.tool_hint == "web_search"
    assert step.status == StepStatus.PENDING
    assert step.sensitive is True
    assert step.result == "Test result"
    assert step.error is None


def test_plan_model_validation():
    """Test Plan model validation with subtasks."""
    plan = Plan(
        goal="Test goal",
        subtasks=[
            Step(id=1, task="Step 1", status=StepStatus.PENDING),
            Step(id=2, task="Step 2", status=StepStatus.PENDING, sensitive=True)
        ]
    )
    
    assert plan.goal == "Test goal"
    assert len(plan.subtasks) == 2
    assert plan.subtasks[0].sensitive is False
    assert plan.subtasks[1].sensitive is True


def test_step_status_enum():
    """Test StepStatus enum values."""
    assert StepStatus.PENDING.value == "PENDING"
    assert StepStatus.RUNNING.value == "RUNNING"
    assert StepStatus.DONE.value == "DONE"
    assert StepStatus.FAILED.value == "FAILED"


@pytest.mark.parametrize("input_task", TEST_INPUTS)
def test_plan_generation(input_task):
    """Test plan generation for various input tasks."""
    graph = build_graph()
    
    initial_state: State = {
        "input": input_task,
        "plan": None
    }
    
    config = {"configurable": {"thread_id": "test-thread"}}
    result = graph.invoke(initial_state, config)
    
    # Verify plan was generated
    assert result["plan"] is not None
    assert isinstance(result["plan"], Plan)
    
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
        assert subtask.result is None  # Initially None
        assert subtask.error is None  # Initially None
    
    print(f"\nInput: {input_task}")
    print(f"Plan: {plan.model_dump_json(indent=2)}")


def test_goa_trip_specific():
    """Specific test for Goa trip planning."""
    graph = build_graph()
    
    initial_state: State = {
        "input": "Plan a weekend trip to Goa",
        "plan": None
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


def test_plan_serialization():
    """Test that Plan can be serialized to JSON and back."""
    original_plan = Plan(
        goal="Test goal",
        subtasks=[
            Step(id=1, task="Step 1", status=StepStatus.PENDING),
            Step(id=2, task="Step 2", status=StepStatus.PENDING, sensitive=True)
        ]
    )
    
    # Serialize to JSON
    json_str = original_plan.model_dump_json(indent=2)
    assert json_str is not None
    
    # Deserialize from JSON
    import json
    data = json.loads(json_str)
    restored_plan = Plan.model_validate(data)
    
    assert restored_plan.goal == original_plan.goal
    assert len(restored_plan.subtasks) == len(original_plan.subtasks)
    assert restored_plan.subtasks[0].task == original_plan.subtasks[0].task
