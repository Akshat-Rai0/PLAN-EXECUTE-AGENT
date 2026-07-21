"""Tests for synthesize_tool_node - dynamic tool synthesis node."""

import pytest
from unittest.mock import patch, MagicMock
from src.agents.plan_execute.nodes import synthesize_tool_node
from src.agents.plan_execute.state import State, Plan, Step, StepStatus
from src.synthesis.schema import SynthesisSchema, SynthesizedTool
from src.synthesis.registry import default_registry


@pytest.fixture(autouse=True)
def clear_registry():
    """Clear the registry before each test to avoid cross-test contamination."""
    default_registry._tools.clear()
    yield
    default_registry._tools.clear()


TEMPERATURE_SCHEMA = SynthesisSchema(
    capability_name="convert_temperature_units",
    description="Converts Fahrenheit temperatures to Celsius and flags which are above freezing.",
    input_description="a JSON object with one key: temps_fahrenheit, a list of floats",
    output_description="a JSON object with celsius_values (list of floats) and above_freezing (list of booleans)",
    example_input={"temps_fahrenheit": [98.6, 32, 212, -40, 75]},
)

TEMPERATURE_CODE = '''
import sys, json

def convert_temperature_units(input_data):
    temps_f = input_data["temps_fahrenheit"]
    celsius = [(t - 32) * 5.0 / 9.0 for t in temps_f]
    above_freezing = [c > 0 for c in celsius]
    return {"celsius_values": celsius, "above_freezing": above_freezing}

input_data = json.loads(sys.argv[1])
result = convert_temperature_units(input_data)
print(json.dumps(result))
'''


def test_synthesize_tool_node_schema_declaration_failure():
    """Test that schema declaration failure marks step as FAILED."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare:
        mock_declare.side_effect = Exception("Schema declaration failed")
        
        result = synthesize_tool_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert "failed to declare schema" in result["plan"].subtasks[0].error


def test_synthesize_tool_node_reuses_existing_tool():
    """Test that an existing tool in registry is reused."""
    # Pre-register a tool
    existing_tool = SynthesizedTool(
        capability_name="convert_temperature_units",
        description=TEMPERATURE_SCHEMA.description,
        input_description=TEMPERATURE_SCHEMA.input_description,
        output_description=TEMPERATURE_SCHEMA.output_description,
        source_code=TEMPERATURE_CODE,
        example_input=TEMPERATURE_SCHEMA.example_input,
        example_output={"celsius_values": [37.0], "above_freezing": [True]},
        times_used=1,
    )
    default_registry.register(existing_tool)
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare:
        mock_declare.return_value = TEMPERATURE_SCHEMA
        
        result = synthesize_tool_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert "reused synthesized tool" in result["plan"].subtasks[0].result
        assert default_registry.get("convert_temperature_units").times_used == 2
    


def test_synthesize_tool_node_falls_back_on_reuse_failure():
    """Test that if reused tool fails on new input, it falls back to resynthesis."""
    # Pre-register a tool that will fail on validation
    existing_tool = SynthesizedTool(
        capability_name="convert_temperature_units",
        description=TEMPERATURE_SCHEMA.description,
        input_description=TEMPERATURE_SCHEMA.input_description,
        output_description=TEMPERATURE_SCHEMA.output_description,
        source_code='print("invalid output")',  # This will fail validation
        example_input=TEMPERATURE_SCHEMA.example_input,
        example_output={},
    )
    default_registry.register(existing_tool)
    
    # Mock validate to fail on first call (reuse) but succeed on second (new synthesis)
    validate_results = [
        MagicMock(success=False, error="Validation failed on reused tool"),
        MagicMock(success=True, output={"celsius_values": [37.0], "above_freezing": [True]}),
    ]
    
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.return_value = TEMPERATURE_CODE
        mock_validate.side_effect = validate_results
        
        result = synthesize_tool_node(state)
        
        # Should have fallen back to synthesis and succeeded
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert "synthesized new tool" in result["plan"].subtasks[0].result
    


def test_synthesize_tool_node_synthesizes_new_tool():
    """Test full synthesis pipeline for a new tool."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.return_value = TEMPERATURE_CODE
        mock_validate.return_value = MagicMock(success=True, output={"celsius_values": [37.0], "above_freezing": [True]})
        
        result = synthesize_tool_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.DONE
        assert "synthesized new tool" in result["plan"].subtasks[0].result
        assert "convert_temperature_units" in result["plan"].subtasks[0].result
        assert default_registry.has("convert_temperature_units")
    


def test_synthesize_tool_node_validation_failure():
    """Test that validation failure after retries marks step as FAILED."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.return_value = 'invalid code'
        mock_validate.return_value = MagicMock(success=False, error="Validation failed")
        
        result = synthesize_tool_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert "failed validation" in result["plan"].subtasks[0].error


def test_synthesize_tool_node_code_generation_failure():
    """Test that code generation failure is handled with retries."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.side_effect = Exception("Code generation failed")
        mock_validate.return_value = MagicMock(success=False, error="Never reached due to generation failure")
        
        result = synthesize_tool_node(state)
        
        assert result["plan"].subtasks[0].status == StepStatus.FAILED
        assert "failed validation" in result["plan"].subtasks[0].error


def test_synthesize_tool_node_no_plan_raises():
    """Test that synthesize_tool_node raises RuntimeError with no plan."""
    state: State = {"input": "test", "plan": None}
    
    with pytest.raises(RuntimeError, match="synthesize_tool_node called with no plan"):
        synthesize_tool_node(state)


def test_synthesize_tool_node_no_running_step_raises():
    """Test that synthesize_tool_node raises RuntimeError with no RUNNING step."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="step 1", tool_hint="synthesize_tool", status=StepStatus.PENDING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with pytest.raises(RuntimeError, match="synthesize_tool_node called with no RUNNING step"):
        synthesize_tool_node(state)


def test_synthesize_tool_node_registers_tool():
    """Test that successful synthesis registers the tool in the registry."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.return_value = TEMPERATURE_CODE
        mock_validate.return_value = MagicMock(success=True, output={"celsius_values": [37.0], "above_freezing": [True]})
        
        synthesize_tool_node(state)
        
        # Check tool was registered
        registered_tool = default_registry.get("convert_temperature_units")
        assert registered_tool is not None
        assert registered_tool.capability_name == "convert_temperature_units"
        assert registered_tool.source_code == TEMPERATURE_CODE
        assert registered_tool.times_used == 1
    


def test_synthesize_tool_node_includes_context_in_schema_declaration():
    """Test that context from prior steps is included in schema declaration."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="search for data", tool_hint="web_search", status=StepStatus.DONE, result="Prior result"),
            Step(id=2, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare:
        mock_declare.return_value = TEMPERATURE_SCHEMA
        
        synthesize_tool_node(state)
        
        # Check that declare_schema was called with context
        call_args = mock_declare.call_args
        assert call_args[0][0] == "test goal"  # goal
        assert call_args[0][1] == "convert temperatures"  # step task
        assert "Prior result" in call_args[0][2]  # context block


def test_synthesize_tool_node_steps_executed_counter():
    """Test that steps_executed counter is incremented."""
    plan = Plan(
        goal="test goal",
        subtasks=[
            Step(id=1, task="convert temperatures", tool_hint="synthesize_tool", status=StepStatus.RUNNING),
        ]
    )
    state: State = {"input": "test", "plan": plan}
    
    with patch('src.agents.plan_execute.nodes.declare_schema') as mock_declare, \
         patch('src.agents.plan_execute.nodes.generate_function_code') as mock_generate, \
         patch('src.agents.plan_execute.nodes.validate_synthesized_function') as mock_validate:
        
        mock_declare.return_value = TEMPERATURE_SCHEMA
        mock_generate.return_value = TEMPERATURE_CODE
        mock_validate.return_value = MagicMock(success=True, output={"celsius_values": [37.0], "above_freezing": [True]})
        
        result = synthesize_tool_node(state)
        
        assert result["steps_executed"] == 1
    
