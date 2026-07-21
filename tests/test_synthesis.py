"""Tests for src/synthesis/ — schema, validator, registry.

codegen.py (the two LLM calls: declare_schema, generate_function_code) is
intentionally NOT tested here with a live LLM — that's covered by
synthesize_tool_node's own tests (test_synthesize_tool_node.py) using
mocked LLM responses, matching this codebase's existing convention for
every other LLM-calling node (test_code_executor_node.py, etc.).

These tests instead validate the parts of the pipeline that don't need an
LLM at all: given a piece of already-generated code (as if codegen.py had
produced it), does validation and registration behave correctly? This is
the same split used by test_delete_file.py (sandbox behavior tested
directly) vs. any future test of delete_file_node (LLM call mocked).
"""

from src.synthesis.schema import SynthesisSchema, SynthesizedTool
from src.synthesis.validator import validate_synthesized_function
from src.synthesis.registry import SynthesisRegistry


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


def test_validate_synthesized_function_success():
    """Uses the exact temperature-conversion case from this project's
    original motivating trace (3 redundant code_executor calls for one
    unit of work) — validates the correct output matches known values.
    """
    result = validate_synthesized_function(TEMPERATURE_CODE, TEMPERATURE_SCHEMA)
    assert result.success
    assert result.output["celsius_values"][0] == 37.0  # 98.6F == 37C
    assert result.output["above_freezing"][1] is False  # 32F == 0C, not above freezing


def test_validate_rejects_crashing_code():
    result = validate_synthesized_function('raise ValueError("oops")', TEMPERATURE_SCHEMA)
    assert not result.success
    assert result.output is None


def test_validate_rejects_non_json_output():
    result = validate_synthesized_function('print("just some text")', TEMPERATURE_SCHEMA)
    assert not result.success
    assert "no JSON object" in result.error


def test_validate_rejects_infinite_loop_via_timeout():
    result = validate_synthesized_function("while True: pass", TEMPERATURE_SCHEMA)
    assert not result.success
    assert "timed out" in result.error.lower()


def test_validate_rejects_empty_dict_output():
    result = validate_synthesized_function(
        'import sys, json; input_data = json.loads(sys.argv[1]); print(json.dumps({}))',
        TEMPERATURE_SCHEMA,
    )
    assert not result.success
    assert "empty" in result.error.lower()


def test_registry_register_and_get():
    registry = SynthesisRegistry()
    tool = SynthesizedTool(
        capability_name="convert_temperature_units",
        description=TEMPERATURE_SCHEMA.description,
        input_description=TEMPERATURE_SCHEMA.input_description,
        output_description=TEMPERATURE_SCHEMA.output_description,
        source_code=TEMPERATURE_CODE,
        example_input=TEMPERATURE_SCHEMA.example_input,
        example_output={"celsius_values": [37.0], "above_freezing": [True]},
    )
    assert not registry.has("convert_temperature_units")
    registry.register(tool)
    assert registry.has("convert_temperature_units")
    assert registry.get("convert_temperature_units").capability_name == "convert_temperature_units"
    assert registry.get("nonexistent_tool") is None
    assert len(registry) == 1


def test_registry_mark_used_increments_counter():
    registry = SynthesisRegistry()
    tool = SynthesizedTool(
        capability_name="test_tool",
        description="d",
        input_description="i",
        output_description="o",
        source_code="pass",
        example_input={},
        example_output={},
    )
    registry.register(tool)
    assert tool.times_used == 0
    registry.mark_used("test_tool")
    registry.mark_used("test_tool")
    assert registry.get("test_tool").times_used == 2


def test_synthesized_tool_approval_summary_includes_source():
    tool = SynthesizedTool(
        capability_name="convert_temperature_units",
        description="Converts F to C.",
        input_description="temps",
        output_description="celsius",
        source_code=TEMPERATURE_CODE,
        example_input={"temps_fahrenheit": [32]},
        example_output={"celsius_values": [0.0]},
    )
    summary = tool.as_approval_summary()
    assert "convert_temperature_units" in summary
    assert TEMPERATURE_CODE.strip() in summary
    assert "Converts F to C." in summary