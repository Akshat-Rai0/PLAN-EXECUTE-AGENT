"""
Data models for sandboxed code execution results.
"""

from typing import Optional
from pydantic import BaseModel


class SandboxResult(BaseModel):
    """
    Result of running a piece of code inside the sandbox.

    `output` is only populated when the script's stdout, on its last
    non-empty line, is valid JSON — this is the convention sandboxed scripts
    are expected to follow (mirrors the existing breakdown_task pattern:
    produce JSON, validate it against a schema). If an `output_schema` was
    passed to run_in_sandbox and the parsed JSON doesn't validate against it,
    `success` is False and `error` explains why, even if the process itself
    exited cleanly — a script that runs successfully but returns garbage is
    still a failure from the caller's point of view.
    """

    success: bool
    stdout: str = ""
    stderr: str = ""
    output: Optional[dict] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    timed_out: bool = False
    duration_seconds: Optional[float] = None
