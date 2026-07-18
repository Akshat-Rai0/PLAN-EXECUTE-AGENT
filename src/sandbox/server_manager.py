"""
Long-running dev server management for the agentic coding sandbox.

Design decisions:
- Uses subprocess.Popen (not subprocess.run) because dev servers run forever.
  The caller gets back control immediately after start() confirms the port is
  open; the server keeps running in the background as a child process.
- Port-readiness polling: instead of a fixed sleep, start() repeatedly tries
  socket.create_connection until the port is open OR the timeout expires OR
  the process exits early (crash detection). This is far more reliable than
  sleeping a fixed amount of time — some servers start in 200ms, some in 10s.
- ServerRegistry: a module-level dict keyed by workspace_path. This is
  necessary because LangGraph nodes are stateless functions; the Popen handle
  must live somewhere that survives between node calls within the same process.
  On the next agent run, stale entries are cleaned up by checking process.poll().
- Graceful stop: SIGTERM first, then wait 5s, then SIGKILL if needed.
"""

import os
import signal
import socket
import subprocess
import time
from typing import Optional

# ---------------------------------------------------------------------------
# Registry — survives between LangGraph node calls within the same OS process
# ---------------------------------------------------------------------------

# {workspace_path: DevServer}
_REGISTRY: dict[str, "DevServer"] = {}


def get_server(workspace_path: str) -> Optional["DevServer"]:
    """Return the DevServer for this workspace if one is registered and alive."""
    server = _REGISTRY.get(workspace_path)
    if server is None:
        return None
    if server.process is not None and server.process.poll() is not None:
        # Process has already exited — clean up the stale entry
        del _REGISTRY[workspace_path]
        return None
    return server


def stop_server(workspace_path: str) -> None:
    """Stop the server for this workspace if one is running."""
    server = _REGISTRY.get(workspace_path)
    if server:
        server.stop()
        _REGISTRY.pop(workspace_path, None)


# ---------------------------------------------------------------------------
# DevServer
# ---------------------------------------------------------------------------

class DevServer:
    """
    Manages a long-running dev server process (npm run dev, vite, uvicorn, etc.)

    Usage:
        server = DevServer(["npm", "run", "dev"], cwd="/tmp/agent-workspaces/myapp-abc123", port=5173)
        result = server.start()
        # result == {"success": True, "url": "http://localhost:5173"}
        # ... later ...
        server.stop()
    """

    def __init__(self, command: list[str], cwd: str, port: int):
        """
        Args:
            command: Argv list (no shell=True). E.g. ["npm", "run", "dev"].
            cwd: Project workspace directory.
            port: The port the server is expected to listen on.
        """
        if not command:
            raise ValueError("command must be a non-empty list")
        if not (1 <= port <= 65535):
            raise ValueError(f"Invalid port: {port}")

        self.command = command
        self.cwd = cwd
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self._started_at: Optional[float] = None

    def start(self, timeout_for_ready: int = 60) -> dict:
        """
        Start the server and block until the port is open (server is ready).

        Args:
            timeout_for_ready: Max seconds to wait for the port to open.
                               Default 60s — enough for Vite HMR startup.

        Returns:
            {"success": True, "url": "http://localhost:<port>", "pid": int}
            or
            {"success": False, "error": str, "stderr": str}
        """
        # Kill any previously registered server for this workspace
        stop_server(self.cwd)

        env = os.environ.copy()
        env["CI"] = "false"  # many dev servers need CI=false to enable HMR

        try:
            self.process = subprocess.Popen(
                self.command,          # shell=False — no shell metacharacters
                cwd=self.cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                # New process group so SIGTERM hits only this tree, not the agent
                start_new_session=True,
            )
        except FileNotFoundError as e:
            return {
                "success": False,
                "error": f"Executable not found: '{self.command[0]}'. Error: {e}",
                "stderr": "",
            }
        except OSError as e:
            return {"success": False, "error": f"Failed to start process: {e}", "stderr": ""}

        self._started_at = time.monotonic()
        deadline = self._started_at + timeout_for_ready

        while time.time() < deadline:
            # Check if process exited early (crash before port opened)
            if self.process.poll() is not None:
                stderr_output = ""
                try:
                    stderr_output = self.process.stderr.read().decode("utf-8", errors="replace")
                except Exception:
                    pass
                return {
                    "success": False,
                    "error": (
                        f"Server process exited early with code {self.process.returncode} "
                        f"before port {self.port} opened."
                    ),
                    "stderr": stderr_output,
                }

            if self._is_port_open():
                # Register ourselves so other parts of the system can find us
                _REGISTRY[self.cwd] = self
                return {
                    "success": True,
                    "url": f"http://localhost:{self.port}",
                    "pid": self.process.pid,
                }

            time.sleep(0.5)

        # Timeout — kill the process and report failure
        self.stop()
        return {
            "success": False,
            "error": (
                f"Server did not open port {self.port} within {timeout_for_ready}s. "
                "Check the server logs for startup errors."
            ),
            "stderr": "",
        }

    def stop(self) -> None:
        """
        Gracefully stop the server process (SIGTERM → wait 5s → SIGKILL).
        Safe to call even if the process has already exited.
        """
        if self.process is None:
            return
        if self.process.poll() is not None:
            # Already exited
            self.process = None
            return

        try:
            # Send SIGTERM to the entire process group (covers child processes
            # spawned by the server, e.g. the Vite HMR worker)
            os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
        except (ProcessLookupError, PermissionError, OSError):
            # Process may have already gone — that's fine
            pass

        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        self.process = None

    def _is_port_open(self) -> bool:
        """Return True if localhost:<self.port> accepts a TCP connection."""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=1):
                return True
        except OSError:
            return False

    def is_running(self) -> bool:
        """Return True if the server process is alive."""
        return self.process is not None and self.process.poll() is None

    @property
    def url(self) -> Optional[str]:
        """Return the server URL if running, else None."""
        return f"http://localhost:{self.port}" if self.is_running() else None


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def start_dev_server(
    command_str: str,
    cwd: str,
    port: int,
    timeout_for_ready: int = 60,
) -> dict:
    """
    Parse `command_str`, create a DevServer, start it, and return the result dict.

    Args:
        command_str: Shell-style command string, e.g. "npm run dev".
                     Tokenized with shlex — shell metacharacters are inert.
        cwd: Project workspace directory (must be under WORKSPACE_BASE).
        port: Expected listen port.
        timeout_for_ready: Seconds to wait for port to open.

    Returns:
        {"success": bool, "url": str|None, "error": str|None, ...}
    """
    import shlex
    from .shell_runner import _assert_within_workspace

    try:
        tokens = shlex.split(command_str)
    except ValueError as e:
        return {"success": False, "error": f"Failed to parse server command: {e}"}

    if not tokens:
        return {"success": False, "error": "Empty server command"}

    try:
        _assert_within_workspace(cwd)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    server = DevServer(command=tokens, cwd=cwd, port=port)
    return server.start(timeout_for_ready=timeout_for_ready)
