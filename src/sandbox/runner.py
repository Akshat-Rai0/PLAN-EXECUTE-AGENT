"""
Core sandboxed code execution.

Security model (per project spec):
- Subprocess isolation: code runs as a separate OS process via `subprocess`,
  never via in-process `eval`/`exec` on raw LLM output.
- Scratch-dir-only filesystem: the subprocess's cwd is a fresh per-run temp
  directory, deleted after execution. This does NOT prevent the process from
  reading/writing arbitrary absolute paths elsewhere on the host — that's a
  real limitation of subprocess-only isolation and is documented in
  LIMITATIONS.md, not silently assumed to be solved.
- Resource caps: hard wall-clock timeout (subprocess.run(timeout=...)) and a
  memory cap enforced via resource.setrlimit(RLIMIT_AS) in the child process,
  set up through a preexec_fn so the limit applies before the child's own
  code starts running.
- No network allowlist yet — see network_guard.py for that piece, applied
  separately; run_in_sandbox() accepts an allowed_domains param but the
  actual enforcement mechanism is intentionally kept in its own module since
  it's the least portable, most OS-dependent piece of this system.

This module deliberately does NOT try to be a full container-grade sandbox
(no true process/network namespace isolation, no seccomp). It is what the
project spec calls "hardened subprocess isolation" — a meaningful, real
security improvement over eval()-ing raw LLM output in-process, but not
equivalent to the containerized (agent-infra/sandbox-style) isolation used
for the separate browser-automation sandbox. This tradeoff is intentional
and documented, not an oversight — see the module docstring in
sandbox/__init__.py for the full writeup on why.
"""

import os
import platform
import resource
import shutil
import subprocess
import tempfile
import time
import uuid
from typing import Optional, Type

from pydantic import BaseModel, ValidationError

from .models import SandboxResult

DEFAULT_TIMEOUT_SECONDS = 15
DEFAULT_MEMORY_LIMIT_MB = 256


def _make_scratch_dir() -> str:
    """Create a fresh, uniquely-named scratch directory for one execution."""
    base = tempfile.gettempdir()
    scratch = os.path.join(base, f"sandbox-run-{uuid.uuid4().hex}")
    os.makedirs(scratch, exist_ok=True)
    return scratch


def _memory_limit_preexec(memory_limit_mb: int):
    """
    Build a preexec_fn that caps the child process's address space (RLIMIT_AS)
    before its own code runs. Linux/macOS only — resource.setrlimit is not
    available on Windows, so this is a no-op there (see _apply_memory_limit).

    RLIMIT_AS caps total virtual memory, not just resident/physical memory —
    this is intentional and stricter, since it catches runaway allocations
    (e.g. building a huge list) even before they're fully touched/paged in.
    """
    memory_limit_bytes = memory_limit_mb * 1024 * 1024

    def _limit():
        try:
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit_bytes, memory_limit_bytes))
        except (ValueError, OSError):
            # Some platforms (notably macOS in certain configurations) don't
            # support RLIMIT_AS reliably. Fail open here rather than crash —
            # the timeout cap still applies regardless, and this is a known,
            # documented limitation rather than a silent gap (see
            # LIMITATIONS.md).
            pass

    return _limit


def _supports_resource_limits() -> bool:
    return platform.system() != "Windows"


def run_in_sandbox(
    code: str,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    memory_limit_mb: int = DEFAULT_MEMORY_LIMIT_MB,
    allowed_domains: Optional[list[str]] = None,
    output_schema: Optional[Type[BaseModel]] = None,
    python_executable: Optional[str] = None,
    args: Optional[list[str]] = None,
) -> SandboxResult:
    """
    Run `code` (a string of Python source) in an isolated subprocess.

    The script is expected to print a single JSON object as the LAST
    non-empty line of stdout if it wants to return structured output — this
    mirrors the existing breakdown_task convention (LLM/script produces
    JSON, caller validates against a Pydantic schema) rather than inventing
    a new protocol.

    Args:
        code: Python source to execute.
        timeout_seconds: Hard wall-clock limit. Process is killed if exceeded.
        memory_limit_mb: Virtual memory cap (RLIMIT_AS) for the child process.
            No-op on Windows — see _supports_resource_limits.
        allowed_domains: If provided, network access is restricted to these
            domains. Enforcement lives in network_guard.py; see that module
            for how it's actually applied (env var + injected sitecustomize,
            not OS-level namespacing).
        output_schema: If provided, stdout's last JSON line is validated
            against this Pydantic model. A script that exits 0 but returns
            output that doesn't match the schema is still SandboxResult(success=False).
        python_executable: Override the interpreter used to run the script.
            Defaults to the current interpreter (sys.executable-equivalent).
        args: Optional list of command-line arguments to pass to the script.
            These will be available as sys.argv[1:] in the executed code.

    Returns:
        SandboxResult — see models.py for field semantics.
    """
    import sys

    python_executable = python_executable or sys.executable
    scratch_dir = _make_scratch_dir()
    script_path = os.path.join(scratch_dir, "script.py")
    network_guard_env: Optional[dict] = None

    try:
        with open(script_path, "w") as f:
            f.write(code)

        preexec_fn = None
        env = os.environ.copy()

        if _supports_resource_limits():
            preexec_fn = _memory_limit_preexec(memory_limit_mb)

        if allowed_domains is not None:
            # Delegate actual enforcement to network_guard — this module
            # only wires the env var the guard's sitecustomize hook reads.
            from .network_guard import prepare_network_restricted_env
            network_guard_env = prepare_network_restricted_env(env, allowed_domains)
            env = dict(network_guard_env)
            # Do not expose runner bookkeeping to the sandboxed process.
            env.pop("_SANDBOX_NETWORK_GUARD_DIR", None)

        start = time.monotonic()
        try:
            cmd = [python_executable, script_path]
            if args:
                cmd.extend(args)
            proc = subprocess.run(
                cmd,
                cwd=scratch_dir,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                preexec_fn=preexec_fn,
                env=env,
            )
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start
            return SandboxResult(
                success=False,
                stdout=e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or ""),
                stderr=e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or ""),
                error=f"Execution timed out after {timeout_seconds}s",
                timed_out=True,
                duration_seconds=duration,
            )

        duration = time.monotonic() - start

        if proc.returncode != 0:
            error_msg = f"Script exited with code {proc.returncode}"
            # RLIMIT_AS exhaustion typically shows up as a MemoryError in
            # stderr or a nonzero exit with no traceback (killed by OOM);
            # surface this distinction where we can detect it, since
            # "generic nonzero exit" isn't actionable for a caller deciding
            # whether to retry.
            if "MemoryError" in proc.stderr:
                error_msg = f"Script exceeded memory limit ({memory_limit_mb}MB)"
            return SandboxResult(
                success=False,
                stdout=proc.stdout,
                stderr=proc.stderr,
                error=error_msg,
                exit_code=proc.returncode,
                duration_seconds=duration,
            )

        result = SandboxResult(
            success=True,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            duration_seconds=duration,
        )

        if output_schema is not None:
            parsed, parse_error = _parse_last_json_line(proc.stdout)
            if parse_error:
                result.success = False
                result.error = parse_error
                return result
            try:
                validated = output_schema.model_validate(parsed)
                result.output = validated.model_dump()
            except ValidationError as e:
                result.success = False
                result.error = f"Output did not match expected schema: {e}"
        elif proc.stdout.strip():
            # No schema given, but still try to surface JSON output if the
            # script produced any — best-effort, not required.
            parsed, _ = _parse_last_json_line(proc.stdout)
            if parsed is not None:
                result.output = parsed

        return result

    finally:
        if network_guard_env is not None:
            from .network_guard import cleanup_network_restricted_env
            cleanup_network_restricted_env(network_guard_env)
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _parse_last_json_line(stdout: str) -> tuple[Optional[dict], Optional[str]]:
    """
    Find the last non-empty line of stdout and try to parse it as JSON.
    Returns (parsed_dict, None) on success, or (None, error_message) if no
    valid JSON line was found.
    """
    import json

    lines = [line for line in stdout.splitlines() if line.strip()]
    if not lines:
        return None, "Script produced no output to parse"

    last_line = lines[-1]
    try:
        parsed = json.loads(last_line)
        if not isinstance(parsed, dict):
            return None, f"Expected a JSON object on the last output line, got {type(parsed).__name__}"
        return parsed, None
    except json.JSONDecodeError as e:
        return None, f"Last output line is not valid JSON: {e}"
