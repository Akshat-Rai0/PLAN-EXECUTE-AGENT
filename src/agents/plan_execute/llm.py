
import os
from langchain.chat_models import OllamaChat,AnthropicChat


if os.getenv("LLM_PROVIDER") == "ollama":
    def get_router_llm():
        model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
        return OllamaChat(model=model, temperature=0)


    def get_llm():
        model = os.getenv("OLLAMA_MODEL", "gemma4:latest")
        return OllamaChat(model=model, temperature=0)
    
elif os.getenv("LLM_PROVIDER") == "anthropic":
    def get_router_llm():
        model = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
        return AnthropicChat(
            model=model,
            temperature=0,
        )

    def get_llm():
        model = os.getenv("CLAUDE_MODEL", "claude-opus-4-8")
        return AnthropicChat(
            model=model,
            temperature=0,
        )