import os
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()


def _build_ollama():
    from langchain_ollama import ChatOllama
    model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
    return ChatOllama(model=model, temperature=0)


def _build_anthropic():
    from langchain_anthropic import ChatAnthropic
    model = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
    return ChatAnthropic(model=model, temperature=0)


def get_llm():
    if LLM_PROVIDER == "ollama":
        return _build_ollama()
    elif LLM_PROVIDER == "anthropic":
        return _build_anthropic()
    raise ValueError(f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}")


def get_router_llm():
    return get_llm()