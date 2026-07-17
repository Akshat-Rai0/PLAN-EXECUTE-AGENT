"""
Outbound network allowlisting for sandboxed code.

HONEST SCOPING NOTE (read this before trusting this module for anything
beyond a portfolio-project security story):

True network isolation is normally done at the OS level — a network
namespace (Linux `unshare --net` + a controlled veth/proxy), a firewall rule
set, or a container runtime's `--network` flag pointed at a restricted proxy.
Those approaches are enforced by the kernel and can't be bypassed by
anything the sandboxed Python code does.

This module does NOT do that. It enforces the allowlist at the Python
socket-library level, inside the very process it's trying to restrict, by
injecting a `sitecustomize.py` that monkeypatches `socket.socket.connect`
(and `getaddrinfo`) to check the target host against the allowlist before
permitting a connection. This is enforced BEFORE the sandboxed script's own
code runs (sitecustomize is imported automatically by the interpreter at
startup), so ordinary sandboxed code — including LLM-generated code using
`requests`, `urllib`, `httpx`, etc., all of which ultimately go through
`socket` — is meaningfully restricted.

What this does NOT stop: sandboxed code that deliberately tries to escape
the restriction by loading a raw C extension that bypasses Python's socket
module, or by re-executing a second Python interpreter without inheriting
PYTHONSTARTUP/sitecustomize. For genuinely adversarial code (as opposed to
LLM-generated code operating in good faith against a declared schema), this
is not a substitute for OS-level enforcement. This tradeoff — and the path
to upgrading it (namespace isolation or a container-based proxy) — should be
called out explicitly in the security writeup, not presented as equivalent
to real network isolation.
"""

import os
import textwrap
from urllib.parse import urlparse

_ALLOWLIST_ENV_VAR = "SANDBOX_ALLOWED_DOMAINS"

_SITECUSTOMIZE_TEMPLATE = '''
import os
import socket
import sys

_ALLOWED = os.environ.get("{env_var}", "").split(",")
_ALLOWED = [d.strip().lower() for d in _ALLOWED if d.strip()]

_original_getaddrinfo = socket.getaddrinfo

def _is_allowed(host):
    if host is None:
        return True
    host = host.lower()
    for allowed in _ALLOWED:
        if host == allowed or host.endswith("." + allowed):
            return True
    return False

def _guarded_getaddrinfo(host, *args, **kwargs):
    if not _is_allowed(host):
        raise OSError(
            f"Network access to '{{host}}' blocked by sandbox allowlist. "
            f"Allowed domains: {{_ALLOWED}}"
        )
    return _original_getaddrinfo(host, *args, **kwargs)

# getaddrinfo is the actual DNS-resolution chokepoint that essentially every
# Python HTTP client (urllib, requests, httpx, aiohttp) routes through
# before opening a socket — patching it here catches connect attempts made
# via hostnames without needing to separately patch every HTTP library.
socket.getaddrinfo = _guarded_getaddrinfo
'''


def prepare_network_restricted_env(env: dict, allowed_domains: list[str]) -> dict:
    """
    Return a modified copy of `env` that, when used to launch a Python
    subprocess, restricts that subprocess's outbound network access to
    `allowed_domains` via an injected sitecustomize.py (see module docstring
    for exactly what this does and does not guarantee).

    Sets:
      - PYTHONPATH prepended with a temp dir containing the sitecustomize
        module, so the interpreter picks it up automatically at startup.
      - SANDBOX_ALLOWED_DOMAINS, read by that sitecustomize module.
    """
    import tempfile
    import uuid

    guard_dir = os.path.join(tempfile.gettempdir(), f"sandbox-netguard-{uuid.uuid4().hex}")
    os.makedirs(guard_dir, exist_ok=True)

    sitecustomize_content = _SITECUSTOMIZE_TEMPLATE.format(env_var=_ALLOWLIST_ENV_VAR)
    with open(os.path.join(guard_dir, "sitecustomize.py"), "w") as f:
        f.write(sitecustomize_content)

    new_env = dict(env)
    existing_pythonpath = new_env.get("PYTHONPATH", "")
    new_env["PYTHONPATH"] = (
        guard_dir + os.pathsep + existing_pythonpath if existing_pythonpath else guard_dir
    )
    new_env[_ALLOWLIST_ENV_VAR] = ",".join(_normalize_domain(d) for d in allowed_domains)

    return new_env


def _normalize_domain(domain: str) -> str:
    """Strip scheme/path if a caller passes a full URL instead of a bare domain."""
    if "://" in domain:
        return urlparse(domain).netloc.lower()
    return domain.lower().strip("/")
