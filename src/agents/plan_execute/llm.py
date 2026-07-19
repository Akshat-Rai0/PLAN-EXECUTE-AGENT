import os
from functools import lru_cache
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

def _build_groq():
    from langchain_groq import ChatGroq
    model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment variables.")
    # max_retries bounds how long a 429 can silently block the CLI — without
    # this the SDK's default retry/backoff can run long enough that a rate
    # limit wait looks indistinguishable from a genuine hang.
    return ChatGroq(model=model, api_key=api_key, temperature=0, max_retries=2, timeout=30)

@lru_cache(maxsize=1)
def get_llm():
    """Return the configured chat client, constructing it once per process.

    LangGraph invokes several nodes for one request and each node may need the
    same provider client.  These clients are safe to reuse and constructing a
    fresh one per node adds connection/setup overhead without changing model
    configuration, which is read from the environment at process startup.
    """
    if LLM_PROVIDER == "ollama":
        return _build_ollama()
    elif LLM_PROVIDER == "anthropic":
        return _build_anthropic()
    elif LLM_PROVIDER == "groq":
        return _build_groq()
    raise ValueError(f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}")


def get_router_llm():
    return get_llm()
