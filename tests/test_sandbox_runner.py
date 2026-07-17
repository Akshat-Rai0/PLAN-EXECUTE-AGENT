"""
Tests for src.sandbox.runner — these run REAL subprocesses (no mocking),
since the entire point of this module is verifying actual OS-level
isolation behavior (timeouts, memory limits, exit codes). Slower than the
rest of the mocked test suite, but that's the correct tradeoff here.
"""

import platform
import pytest
from pydantic import BaseModel

from src.sandbox.runner import run_in_sandbox
from src.sandbox.models import SandboxResult


def test_simple_success():
    result = run_in_sandbox("print('hello from sandbox')")
    assert result.success is True
    assert "hello from sandbox" in result.stdout
    assert result.exit_code == 0
    assert result.timed_out is False


def test_script_with_syntax_error():
    result = run_in_sandbox("this is not valid python !!!")
    assert result.success is False
    assert result.exit_code != 0
    assert result.error is not None


def test_script_raises_exception():
    result = run_in_sandbox("raise ValueError('deliberate test failure')")
    assert result.success is False
    assert "Script exited with code" in result.error
    assert "ValueError" in result.stderr


def test_timeout_enforced():
    result = run_in_sandbox("import time\ntime.sleep(30)", timeout_seconds=2)
    assert result.success is False
    assert result.timed_out is True
    assert "timed out" in result.error.lower()
    # Should not have waited anywhere near the full 30s
    assert result.duration_seconds is not None
    assert result.duration_seconds < 10


def test_scratch_dir_is_cwd():
    """The script's cwd should be a scratch dir, and it should be able to
    write a file there without error (it's isolated, not that writes are
    forbidden entirely — see module docstring for what this does/doesn't
    guarantee about filesystem isolation)."""
    code = """
import os
with open("test_output.txt", "w") as f:
    f.write("wrote to scratch dir")
print("ok, cwd is:", os.getcwd())
"""
    result = run_in_sandbox(code)
    assert result.success is True
    assert "ok, cwd is:" in result.stdout


def test_scratch_dir_cleaned_up_after_run():
    """The scratch dir should not persist after the run completes."""
    import os
    code = "import os; print(os.getcwd())"
    result = run_in_sandbox(code)
    assert result.success is True
    scratch_dir_path = result.stdout.strip()
    assert not os.path.exists(scratch_dir_path), \
        "Scratch dir should be deleted after the sandboxed run completes"


# --- Output schema validation ---------------------------------------------

class _ExampleOutputSchema(BaseModel):
    value: int
    label: str


def test_output_schema_validation_success():
    code = 'print(\'{"value": 42, "label": "test"}\')'
    result = run_in_sandbox(code, output_schema=_ExampleOutputSchema)
    assert result.success is True
    assert result.output == {"value": 42, "label": "test"}


def test_output_schema_validation_failure_wrong_shape():
    code = 'print(\'{"value": "not an int", "label": "test"}\')'
    result = run_in_sandbox(code, output_schema=_ExampleOutputSchema)
    assert result.success is False
    assert "did not match expected schema" in result.error.lower()


def test_output_schema_validation_no_json_output():
    code = 'print("just plain text, not json")'
    result = run_in_sandbox(code, output_schema=_ExampleOutputSchema)
    assert result.success is False
    assert result.error is not None


def test_no_schema_still_captures_json_if_present():
    """Without an explicit output_schema, valid trailing JSON is still
    surfaced in .output on a best-effort basis."""
    code = 'print(\'{"anything": "goes"}\')'
    result = run_in_sandbox(code)
    assert result.success is True
    assert result.output == {"anything": "goes"}


def test_no_schema_no_json_output_still_succeeds():
    """A script with no JSON output and no schema requirement should still
    be considered successful if it exits 0 — JSON output is opt-in via
    output_schema, not mandatory."""
    code = 'print("hello, no json here")'
    result = run_in_sandbox(code)
    assert result.success is True
    assert result.output is None


# --- Memory limit ------------------------------------------------------

@pytest.mark.skipif(
    platform.system() == "Windows",
    reason="RLIMIT_AS memory limiting is not supported on Windows"
)
def test_memory_limit_enforced():
    """A script that tries to allocate far more than the memory cap should
    fail (either MemoryError inside the script, or a nonzero exit from the
    OS killing it)."""
    code = """
data = []
# Attempt to allocate ~2GB in chunks — should exceed a 256MB (default) cap.
for _ in range(2000):
    data.append(bytearray(1024 * 1024))
print("should not reach here")
"""
    result = run_in_sandbox(code, memory_limit_mb=64, timeout_seconds=10)
    assert result.success is False
