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
DEFAULT_READY_TIMEOUT_SECONDS = 15
READY_POLL_INTERVAL_SECONDS = 0.2
PORT_CHECK_TIMEOUT_SECONDS = 0.2


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

    def start(self, timeout_for_ready: int = DEFAULT_READY_TIMEOUT_SECONDS) -> dict:
        """
        Start the server and block until the port is open (server is ready).

        Args:
            timeout_for_ready: Max seconds to wait for the port to open.
                               Defaults to 15s. Set a larger value only for a
                               known slow server, so failed startups do not
                               occupy a worker for a full minute.

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
                # Without this the child inherits our stdin. Some dev servers
                # (Vite included) prompt interactively if the requested port
                # is already in use — e.g. "Port 5173 is in use, try another
                # one? (Y/n)" — and will sit waiting on stdin for an answer
                # that can never come in this environment, silently eating
                # the full timeout_for_ready window before we report a
                # generic "port never opened" error with no indication why.
                # Closing stdin makes the server see EOF immediately, so a
                # well-behaved one fails fast with a real error instead.
                stdin=subprocess.DEVNULL,
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

        # `deadline` is based on monotonic time, so compare it to the same
        # clock. Mixing in time.time() makes the deadline nonsensical and can
        # cause immediate readiness failures.
        while time.monotonic() < deadline:
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

            time.sleep(READY_POLL_INTERVAL_SECONDS)

        # Timeout — capture whatever output the process produced before we
        # kill it. Previously this branch hardcoded stderr="", which meant
        # every timeout failure reported only "check the server logs" with
        # no logs actually surfaced — leaving the replanner (and the human
        # at the approval gate) unable to tell a real startup error (e.g.
        # "Cannot find module", a port conflict, a missing env var) apart
        # from a merely-slow-starting server.
        #
        # Must read BEFORE calling stop() — stop() nulls self.process once
        # the child is killed, so the pipe handles are unreachable after.
        # The process is still running at this point (we only got here by
        # falling out of the polling loop, not via the early-exit branch
        # above), so a plain blocking .read() would hang forever waiting
        # for EOF. Make each pipe's fd non-blocking first so read() returns
        # immediately with whatever is currently buffered, even if the
        # process is still alive and the pipe hasn't closed.
        stderr_output = ""
        stdout_output = ""
        try:
            import fcntl

            for stream, attr in ((self.process.stderr, "stderr"), (self.process.stdout, "stdout")):
                if stream is None:
                    continue
                fd = stream.fileno()
                flags = fcntl.fcntl(fd, fcntl.F_GETFL)
                fcntl.fcntl(fd, fcntl.F_SETFL, flags | os.O_NONBLOCK)
                try:
                    chunk = stream.read()
                except (BlockingIOError, TypeError):
                    chunk = b""
                if chunk:
                    text = chunk.decode("utf-8", errors="replace")
                    if attr == "stderr":
                        stderr_output = text
                    else:
                        stdout_output = text
        except Exception:
            # Best-effort — if this fails for any reason (e.g. non-POSIX
            # platform, already-closed pipe), fall back to empty strings
            # rather than let output-capture itself break the timeout path.
            pass

        self.stop()
        return {
            "success": False,
            "error": (
                f"Server did not open port {self.port} within {timeout_for_ready}s. "
                "Check the server logs for startup errors."
            ),
            "stderr": stderr_output,
            "stdout": stdout_output,
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
            with socket.create_connection(
                ("localhost", self.port), timeout=PORT_CHECK_TIMEOUT_SECONDS
            ):
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
    timeout_for_ready: int = DEFAULT_READY_TIMEOUT_SECONDS,
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
