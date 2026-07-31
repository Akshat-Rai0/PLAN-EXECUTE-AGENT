"""Configuration tests for the OpenRouter-backed agentic LLM."""

from unittest.mock import patch

from src.agents.plan_execute import llm


def test_openrouter_provider_builds_free_nemotron_model(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.delenv("OPENROUTER_MODEL", raising=False)

    with patch("langchain_openai.ChatOpenAI") as chat_openai:
        llm._build_openrouter()

    kwargs = chat_openai.call_args.kwargs
    assert kwargs["model"] == "nvidia/nemotron-3-ultra-550b-a55b:free"
    assert kwargs["base_url"] == "https://openrouter.ai/api/v1"
