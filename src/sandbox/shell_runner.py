"""
Sandboxed shell command execution and workspace management.

Security model:
- shell=False always: commands are tokenized via shlex.split() and exec'd
  directly, so shell metacharacters (&&, ;, |, $(), backticks) are treated
  as literal characters, not shell syntax. This is the single most important
  rule — never pass shell=True to any subprocess call in this module.
- Allowlist enforcement: only commands whose argv[0] is in ALLOWED_COMMANDS
  will execute. Everything else is rejected before a subprocess is spawned.
- Workspace confinement: the cwd of every subprocess is resolved to a real
  path (following symlinks) and checked to be under the agent-workspaces
  base directory before execution. This prevents path-traversal tricks.
- Timeout: every command has a hard wall-clock timeout (default 120s for
  installs, 30s for quick ops). Processes that exceed it are killed.

What this does NOT provide:
- OS-level process/network namespacing (no seccomp, no Linux namespaces).
- True filesystem isolation — the sandboxed process can still open absolute
  paths outside the workspace IF the OS allows it. The workspace-confinement
  check only ensures the subprocess's cwd starts inside the workspace; it
  doesn't prevent the subprocess from doing os.chdir('/') itself.
- For production use, wrap this in Docker (see docs/system-wiring.html for
  the upgrade path).
"""

import os
import shlex
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Base directory for all agent-managed project workspaces.
WORKSPACE_BASE = Path(tempfile.gettempdir()) / "agent-workspaces"

# Commands the agent is allowed to run. Checked against argv[0] only.
# Extend carefully — every entry here is a potential privilege-escalation
# surface if the agent can be tricked into passing adversarial arguments.
ALLOWED_COMMANDS = {
    "mkdir",
    "touch",
    "ls",
    "cat",
    "echo",
    "cp",
    "mv",
    "node",
    "npm",
    "npx",
    "python3",
    "python",
    "pip",
    "pip3",
    "git",
    "sh",         # needed for some npx scaffolders that shell out
    "bash",       # same
    "which",
    "pwd",
}

DEFAULT_QUICK_TIMEOUT = 30    # seconds — for ls, mkdir, cat, etc.
DEFAULT_INSTALL_TIMEOUT = 180  # seconds — for npm install, pip install, etc.

# Commands that typically need a longer timeout (package installs, scaffolding)
_INSTALL_COMMANDS = {"npm", "npx", "pip", "pip3"}


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

class ShellResult(BaseModel):
    """Result of a sandboxed shell command execution."""

    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: Optional[int] = None
    error: Optional[str] = None
    duration_seconds: Optional[float] = None
    command: str = ""
    cwd: str = ""


# ---------------------------------------------------------------------------
# Workspace management
# ---------------------------------------------------------------------------

def make_project_workspace(name: str) -> str:
    """
    Create a fresh, uniquely-named persistent directory for one project session.

    Unlike the ephemeral scratch dirs in runner.py (which are deleted after
    each run), this directory survives across multiple node calls for the
    lifetime of the agent run. The agent's graph threads workspace_path
    through state so every subsequent node can find it.

    Args:
        name: Human-readable project name (e.g. "todo-app"). Sanitized before
              use — only alphanumerics, hyphens, underscores.

    Returns:
        Absolute path to the created workspace directory.
    """
    # Sanitize the name so it's safe as a directory component
    safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "-" for c in name)
    safe_name = safe_name[:40] or "project"  # cap length, fallback if blank

    WORKSPACE_BASE.mkdir(parents=True, exist_ok=True)
    workspace = WORKSPACE_BASE / f"{safe_name}-{uuid.uuid4().hex[:8]}"
    workspace.mkdir(parents=True, exist_ok=True)
    return str(workspace)


def _assert_within_workspace(cwd: str) -> None:
    """
    Raise ValueError if `cwd` is not under WORKSPACE_BASE.

    Resolves symlinks before checking so a crafted symlink can't escape.
    """
    resolved = Path(os.path.realpath(cwd))
    base = Path(os.path.realpath(str(WORKSPACE_BASE)))
    if not (resolved == base or str(resolved).startswith(str(base) + os.sep)):
        raise ValueError(
            f"cwd '{cwd}' is outside the agent workspace base '{WORKSPACE_BASE}'. "
            "All shell commands must run inside an agent-managed workspace."
        )


# ---------------------------------------------------------------------------
# Shell command execution
# ---------------------------------------------------------------------------

def run_shell_command(
    command: str,
    cwd: str,
    timeout_seconds: Optional[int] = None,
    allowed_commands: Optional[set] = None,
    env_overrides: Optional[dict] = None,
) -> ShellResult:
    """
    Run a shell command inside the agent workspace.

    Args:
        command: The command string to execute (e.g. "npm install react").
                 Parsed via shlex.split — shell metacharacters are INERT.
        cwd: Working directory. MUST be inside WORKSPACE_BASE.
        timeout_seconds: Hard kill timeout. Defaults to INSTALL_TIMEOUT for
                         npm/npx/pip, QUICK_TIMEOUT for everything else.
        allowed_commands: Override the global ALLOWED_COMMANDS set for this
                          call. None means use the global set.
        env_overrides: Extra environment variables to merge into the child's
                       environment (e.g. {"NODE_ENV": "development"}).

    Returns:
        ShellResult with success/stdout/stderr/exit_code/error/duration.
    """
    try:
        tokens = shlex.split(command)
    except ValueError as e:
        return ShellResult(
            success=False,
            error=f"Failed to parse command: {e}",
            command=command,
            cwd=cwd,
        )

    if not tokens:
        return ShellResult(
            success=False,
            error="Empty command",
            command=command,
            cwd=cwd,
        )

    binary = tokens[0]
    allowlist = allowed_commands if allowed_commands is not None else ALLOWED_COMMANDS

    # --- Allowlist check ---
    if binary not in allowlist:
        return ShellResult(
            success=False,
            error=(
                f"Command '{binary}' is not in the allowed command list. "
                f"Allowed: {sorted(allowlist)}"
            ),
            command=command,
            cwd=cwd,
        )

    # --- Workspace confinement check ---
    try:
        _assert_within_workspace(cwd)
    except ValueError as e:
        return ShellResult(
            success=False,
            error=str(e),
            command=command,
            cwd=str(cwd),
        )

    # --- Ensure cwd exists ---
    if not os.path.isdir(cwd):
        return ShellResult(
            success=False,
            error=f"Working directory does not exist: {cwd}",
            command=command,
            cwd=cwd,
        )

    # --- Timeout selection ---
    if timeout_seconds is None:
        timeout_seconds = DEFAULT_INSTALL_TIMEOUT if binary in _INSTALL_COMMANDS else DEFAULT_QUICK_TIMEOUT

    # --- Environment ---
    env = os.environ.copy()
    # Prevent interactive prompts from stalling the subprocess
    env.setdefault("CI", "true")
    env.setdefault("npm_config_yes", "true")
    if env_overrides:
        env.update(env_overrides)

    start = time.monotonic()
    try:
        proc = subprocess.run(
            tokens,           # shell=False — no shell metacharacter interpretation
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            env=env,
        )
    except subprocess.TimeoutExpired as e:
        duration = time.monotonic() - start
        stdout = e.stdout.decode() if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = e.stderr.decode() if isinstance(e.stderr, bytes) else (e.stderr or "")
        return ShellResult(
            success=False,
            stdout=stdout,
            stderr=stderr,
            error=f"Command timed out after {timeout_seconds}s: {command}",
            duration_seconds=duration,
            command=command,
            cwd=cwd,
        )
    except FileNotFoundError:
        return ShellResult(
            success=False,
            error=f"Executable not found: '{binary}'. Is it installed on this system?",
            command=command,
            cwd=cwd,
        )

    duration = time.monotonic() - start

    if proc.returncode != 0:
        return ShellResult(
            success=False,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
            error=f"Command exited with code {proc.returncode}",
            duration_seconds=duration,
            command=command,
            cwd=cwd,
        )

    return ShellResult(
        success=True,
        stdout=proc.stdout,
        stderr=proc.stderr,
        exit_code=proc.returncode,
        duration_seconds=duration,
        command=command,
        cwd=cwd,
    )


# ---------------------------------------------------------------------------
# File writing
# ---------------------------------------------------------------------------

def write_file(relative_path: str, content: str, workspace_path: str) -> dict:
    """
    Write a file into the workspace at `relative_path`.

    relative_path must be a relative path (no leading /). Parent directories
    are created automatically. The final resolved path is checked to be inside
    the workspace before writing.

    Args:
        relative_path: Path relative to workspace_path (e.g. "src/App.jsx").
        content: File content to write (UTF-8).
        workspace_path: Absolute path to the project workspace.

    Returns:
        dict with keys: success (bool), path (str), bytes_written (int), error (str|None).
    """
    # Reject absolute paths from the LLM — only relative paths are safe here
    if os.path.isabs(relative_path):
        return {
            "success": False,
            "error": f"relative_path must be relative, not absolute: '{relative_path}'",
        }

    # Build and resolve the full path
    full_path = Path(workspace_path) / relative_path
    try:
        resolved = Path(os.path.realpath(str(full_path.parent)))
        base = Path(os.path.realpath(workspace_path))
        # Normalise: resolved must be inside base (or equal to it)
        if not (resolved == base or str(resolved).startswith(str(base) + os.sep)):
            return {
                "success": False,
                "error": (
                    f"Resolved path '{full_path}' escapes the workspace. "
                    "Path traversal (../../) is not allowed."
                ),
            }
    except Exception as e:
        return {"success": False, "error": f"Path resolution error: {e}"}

    try:
        full_path.parent.mkdir(parents=True, exist_ok=True)
        encoded = content.encode("utf-8")
        full_path.write_bytes(encoded)
        return {
            "success": True,
            "path": str(full_path),
            "bytes_written": len(encoded),
            "error": None,
        }
    except OSError as e:
        return {"success": False, "error": f"Failed to write file: {e}"}
