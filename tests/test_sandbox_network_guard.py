"""
Tests for src.sandbox.network_guard's allowlist enforcement.

These run real subprocesses that attempt real DNS resolution — no live
network calls succeed/fail here in a way that depends on actual internet
connectivity, since we're testing that BLOCKED hosts raise before any
connection is attempted, and allowed-but-nonexistent hosts fail for
resolution reasons unrelated to the guard (both are fine for this test's
purpose — we're asserting the guard's decision, not real network reachability).
"""

from src.sandbox.runner import run_in_sandbox
from src.sandbox.network_guard import _normalize_domain, prepare_network_restricted_env


def test_disallowed_domain_blocked():
    code = """
import socket
try:
    socket.getaddrinfo("evil-not-allowed.example.com", 443)
    print('{"blocked": false}')
except OSError as e:
    print('{"blocked": true}')
"""
    result = run_in_sandbox(code, allowed_domains=["api.tavily.com"])
    assert result.success is True
    assert result.output == {"blocked": True}


def test_allowed_domain_not_blocked_by_guard():
    """
    The guard itself should not raise for an allowed domain — whether the
    actual DNS resolution succeeds depends on real network availability in
    the test environment, which we don't assert on here. We only assert
    the guard didn't reject it outright (i.e. no "blocked by sandbox
    allowlist" OSError specifically).
    """
    code = """
import socket
try:
    socket.getaddrinfo("api.tavily.com", 443)
    print('{"blocked_by_guard": false}')
except OSError as e:
    msg = str(e)
    print('{"blocked_by_guard": ' + ("true" if "sandbox allowlist" in msg else "false") + '}')
"""
    result = run_in_sandbox(code, allowed_domains=["api.tavily.com"])
    assert result.success is True
    assert result.output == {"blocked_by_guard": False}


def test_subdomain_of_allowed_domain_permitted():
    code = """
import socket
try:
    socket.getaddrinfo("sub.api.tavily.com", 443)
    print('{"blocked_by_guard": false}')
except OSError as e:
    msg = str(e)
    print('{"blocked_by_guard": ' + ("true" if "sandbox allowlist" in msg else "false") + '}')
"""
    result = run_in_sandbox(code, allowed_domains=["api.tavily.com"])
    assert result.success is True
    assert result.output == {"blocked_by_guard": False}


def test_no_network_restriction_when_allowed_domains_none():
    """When allowed_domains is not passed at all (None), no guard should be
    injected — network calls proceed unrestricted by this module."""
    code = """
import os
guard_active = "SANDBOX_ALLOWED_DOMAINS" in os.environ
print('{"guard_active": ' + str(guard_active).lower() + '}')
"""
    result = run_in_sandbox(code)  # allowed_domains not passed
    assert result.success is True
    assert result.output == {"guard_active": False}


# --- _normalize_domain helper --------------------------------------------

def test_normalize_domain_bare():
    assert _normalize_domain("api.tavily.com") == "api.tavily.com"


def test_normalize_domain_strips_scheme_and_path():
    assert _normalize_domain("https://api.tavily.com/v1/search") == "api.tavily.com"


def test_normalize_domain_lowercases():
    assert _normalize_domain("API.Tavily.COM") == "api.tavily.com"


# --- prepare_network_restricted_env ---------------------------------------

def test_prepare_env_sets_allowlist_var():
    env = prepare_network_restricted_env({}, ["api.tavily.com", "fifa.com"])
    assert env["SANDBOX_ALLOWED_DOMAINS"] == "api.tavily.com,fifa.com"


def test_prepare_env_sets_pythonpath():
    env = prepare_network_restricted_env({}, ["api.tavily.com"])
    assert "PYTHONPATH" in env
    assert env["PYTHONPATH"]  # non-empty


def test_prepare_env_preserves_existing_pythonpath():
    original_env = {"PYTHONPATH": "/some/existing/path"}
    env = prepare_network_restricted_env(original_env, ["api.tavily.com"])
    assert "/some/existing/path" in env["PYTHONPATH"]
