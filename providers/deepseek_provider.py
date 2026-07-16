"""
DeepSeek provider. Thin subclass — DeepSeek's API is documented as
OpenAI-SDK-compatible, so all translation logic is shared with
_openai_compatible.py; this file only sets the base_url, default model,
and API key.
"""

from providers._openai_compatible import OpenAICompatibleProvider

DEEPSEEK_BASE_URL = "https://api.deepseek.com"

# "deepseek-v4-pro" is the current non-legacy flagship model name as of
# this writing. "deepseek-chat" also still works as a legacy alias (the
# non-thinking mode of v4-flash) but is scheduled for retirement — check
# https://api-docs.deepseek.com/ if this default seems stale.
DEFAULT_MODEL = "deepseek-v4-pro"


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"

    def __init__(self, api_key: str, model: str = None, max_tokens: int = 4096):
        super().__init__(
            api_key=api_key, model=model or DEFAULT_MODEL, base_url=DEEPSEEK_BASE_URL, max_tokens=max_tokens
        )
