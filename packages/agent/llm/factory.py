import os

from dotenv import load_dotenv

from packages.agent.llm.base import LLMProvider
from packages.agent.llm.gemini import GeminiProvider
from packages.agent.llm.ollama_provider import OllamaProvider
from packages.agent.llm.groq_provider import GroqProvider


# Loaded once, at import time, so every entrypoint (CLI scripts, the API
# server, tests) picks up .env without needing to call this explicitly.
load_dotenv()


def get_llm_provider() -> LLMProvider:
    provider = os.getenv(
        "LLM_PROVIDER",
        "ollama",
    ).lower().strip()

    if provider == "gemini":
        return GeminiProvider()

    if provider == "ollama":
        return OllamaProvider()

    if provider == "groq":
        return GroqProvider()

    raise RuntimeError(
        f"Unsupported LLM provider: {provider}"
    )