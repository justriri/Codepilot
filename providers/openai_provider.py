"""
OpenAI provider. Thin subclass — all translation logic lives in
_openai_compatible.py since OpenAI's API is what that format is modeled on.
"""

from providers._openai_compatible import OpenAICompatibleProvider

# "gpt-5.6" is OpenAI's flagship-routing alias (points to the Sol tier)
# as of this writing. Verify at https://platform.openai.com/docs/models
# if this default seems out of date by the time you're reading this —
# model names change faster than code comments do.
DEFAULT_MODEL = "gpt-5.6"


class OpenAIProvider(OpenAICompatibleProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str = None, max_tokens: int = 4096):
        super().__init__(api_key=api_key, model=model or DEFAULT_MODEL, base_url=None, max_tokens=max_tokens)
