"""
Hardened subprocess isolation for code-exec and (later) dynamic tool
synthesis.

Public API:
    from src.sandbox.runner import run_in_sandbox
    from src.sandbox.models import SandboxResult

Security posture (see runner.py and network_guard.py for full detail):
    - Subprocess isolation, never in-process eval/exec on raw LLM output.
    - Scratch-dir cwd, deleted after each run.
    - Hard timeout + memory cap (RLIMIT_AS) per execution.
    - Best-effort network allowlisting via a socket.getaddrinfo patch
      injected through sitecustomize — Python-level enforcement, NOT
      OS-level network namespace isolation. Sufficient for LLM-generated
      code operating in good faith against a declared schema; not a
      defense against genuinely adversarial code trying to escape the
      sandbox. See network_guard.py's module docstring for the honest
      scoping writeup — this distinction should be stated explicitly in
      any security review of this project, not glossed over.
    - Output schema validation on exit via Pydantic, mirroring the existing
      breakdown_task convention (script prints JSON, caller validates).

Deliberately NOT implemented here: full container/namespace isolation
(seccomp, network namespaces, read-only root filesystem). The project's
separate browser-automation sandbox uses a containerized runtime
(agent-infra/sandbox) for that stronger isolation profile; this module is
the lighter "hardened subprocess isolation" tier the spec calls for the
code-exec path, not a claim of equivalent security to a container.
"""
