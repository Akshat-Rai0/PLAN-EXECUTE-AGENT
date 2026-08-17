import os
from functools import lru_cache
from dotenv import load_dotenv

load_dotenv()

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openrouter").lower()


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
    model = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY is not set in the environment variables.")
    # max_retries bounds how long a 429 can silently block the CLI — without
    # this the SDK's default retry/backoff can run long enough that a rate
    # limit wait looks indistinguishable from a genuine hang.
    return ChatGroq(model=model, api_key=api_key, temperature=0, max_retries=2, timeout=30)


def _build_openrouter():
    """Build the main agent LLM with OpenRouter's free Nemotron model."""
    from langchain_openai import ChatOpenAI

    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set in the environment variables.")
    return ChatOpenAI(
        model=os.getenv("OPENROUTER_MODEL", "nvidia/nemotron-3-ultra-550b-a55b:free"),
        api_key=api_key,
        base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        temperature=0,
        max_retries=2,
        timeout=30,
    )

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
    elif LLM_PROVIDER == "openrouter":
        return _build_openrouter()
    raise ValueError(f"Unknown LLM_PROVIDER={LLM_PROVIDER!r}")


def get_cheap_llm():
    """Return a cheaper/faster model for simple verification tasks."""
    if LLM_PROVIDER == "groq":
        from langchain_groq import ChatGroq
        model = "openai/gpt-oss-120b"
        api_key = os.getenv("GROQ_API_KEY")
        return ChatGroq(model=model, api_key=api_key, temperature=0, max_retries=2, timeout=10)
    elif LLM_PROVIDER == "openrouter":
        from langchain_openai import ChatOpenAI
        api_key = os.getenv("OPENROUTER_API_KEY")
        model = os.getenv("BROWSER_USE_MODEL", "google/gemma-4-31b-it:free")
        return ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            temperature=0,
            max_retries=2,
            timeout=10,
        )
    # Fallback to the main LLM if provider isn't specially handled
    return get_llm()


def get_router_llm():
    return get_llm()
