import pytest
from typing import TypedDict, Optional


class State(TypedDict):
    """State with input, plan, and output."""
    input: str
    plan: Optional[str]
    output: str


def test_state_structure():
    """Test that State has the required fields."""
    state: State = {
        "input": "test input",
        "plan": "test plan",
        "output": "test output"
    }
    
    assert state["input"] == "test input"
    assert state["plan"] == "test plan"
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
    state: State = {
        "input": "Write a hello world program",
        "plan": "Step 1 → Step 2 → Step 3",
        "output": "Step 1 → Step 2 → Step 3"
    }
    
    assert isinstance(state["input"], str)
    assert isinstance(state["plan"], str) or state["plan"] is None
    assert isinstance(state["output"], str)
