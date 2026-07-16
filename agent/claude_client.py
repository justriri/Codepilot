"""
DEPRECATED as of the multi-provider architecture.

This class's logic now lives in providers/anthropic_provider.py
(AnthropicProvider), which implements the same underlying API calls but
behind the provider-neutral BaseProvider interface so DebuggingAgent and
AgentController work with any configured provider (Anthropic, DeepSeek,
OpenAI, local models) — see providers/router.py.

Kept in the repo only as a historical reference. Nothing imports this
file anymore.
"""

import anthropic


class ClaudeClient:
    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def send(self, messages: list, tools: list, system: str):
        return self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=messages,
            tools=tools,
        )
