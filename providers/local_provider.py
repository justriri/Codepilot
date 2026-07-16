"""
Local model provider. Thin subclass targeting any OpenAI-compatible
local server — Ollama's OpenAI-compatible endpoint is the most common
choice and is what the default base_url below assumes, but any
compatible local server works by overriding LOCAL_MODEL_BASE_URL.

No real API key is needed for most local servers, but the OpenAI SDK
requires a non-empty string, so a placeholder is used unless one is
configured.

UNVERIFIED IN THIS ENVIRONMENT: there's no local model server available
here to test against — this is built to the documented Ollama
OpenAI-compatibility contract but hasn't been exercised against a real
running instance. Worth confirming on your machine before relying on it.
"""

from providers._openai_compatible import OpenAICompatibleProvider

DEFAULT_BASE_URL = "http://localhost:11434/v1"  # Ollama's OpenAI-compatible endpoint


class LocalProvider(OpenAICompatibleProvider):
    name = "local"

    def __init__(self, model: str, base_url: str = None, api_key: str = None, max_tokens: int = 4096):
        if not model:
            raise ValueError(
                "LocalProvider requires an explicit model name (whatever you've pulled "
                "locally, e.g. 'llama3.1') — there's no universal default for local models."
            )
        super().__init__(
            api_key=api_key or "not-needed-for-local",
            model=model,
            base_url=base_url or DEFAULT_BASE_URL,
            max_tokens=max_tokens,
        )
