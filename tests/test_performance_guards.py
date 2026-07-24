"""Regression tests for bounded prompt and startup-performance safeguards."""

from unittest.mock import MagicMock, patch

from src.agents.plan_execute import llm
from src.agents.react.nodes import MAX_HISTORY_CHARS_IN_PROMPT, _render_history, react_step
from src.agents.react.state import Turn, ReactState
from src.sandbox.server_manager import DevServer, stop_server


def test_llm_client_is_cached_per_process(monkeypatch):
    llm.get_llm.cache_clear()
    client = object()
    monkeypatch.setattr(llm, "LLM_PROVIDER", "ollama")
    with patch.object(llm, "_build_ollama", return_value=client) as build:
        assert llm.get_llm() is client
        assert llm.get_llm() is client
        build.assert_called_once()
    llm.get_llm.cache_clear()


def test_react_history_is_bounded_to_recent_compact_turns():
    history = [
        Turn(
            thought=f"thought {index}",
            action="web_search",
            action_input="query " + ("x" * 2_000),
            observation="result " + ("y" * 2_000),
        )
        for index in range(10)
    ]

    rendered = _render_history(history)

    assert "Earlier " in rendered
    assert "thought 0" not in rendered
    assert "thought 9" in rendered
    # Prefix text is intentionally outside the compact payload budget.
    assert len(rendered) <= MAX_HISTORY_CHARS_IN_PROMPT + 100


def test_react_prompt_does_not_teach_bash_wrapped_shell_commands():
    mock_response = MagicMock()
    mock_response.content = "Thought: done\nAction: final_answer\nAction Input: ok"

    state: ReactState = {
        "goal": "create a simple script",
        "history": [],
        "final_answer": None,
        "iterations": 0,
        "workspace_path": None,
    }

    with patch("src.agents.react.nodes.get_llm") as mock_get_llm:
        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response
        mock_get_llm.return_value = mock_llm

        react_step(state)

        prompt_content = mock_llm.invoke.call_args[0][0][1].content
        assert "use bash -c" not in prompt_content.lower()
        assert "Pass the literal command you want executed directly" in prompt_content


def test_server_readiness_uses_monotonic_deadline():
    process = MagicMock()
    process.poll.return_value = None
    process.pid = 12345
    server = DevServer(["python3", "-m", "http.server"], cwd=".", port=8765)

    with patch("src.sandbox.server_manager.subprocess.Popen", return_value=process), \
         patch.object(DevServer, "_is_port_open", return_value=True), \
         patch("src.sandbox.server_manager.time.monotonic", side_effect=[10.0, 10.1]), \
         patch("src.sandbox.server_manager.time.time", return_value=1_000_000.0):
        result = server.start(timeout_for_ready=1)

    assert result["success"] is True
    assert result["url"] == "http://localhost:8765"
    stop_server(".")
