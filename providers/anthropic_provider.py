"""
Anthropic provider.

Wraps the `anthropic` SDK. This is where agent/claude_client.py's logic
now lives — see that file for a pointer here.

Anthropic's own wire format is close enough to this codebase's normalized
format that translation is mostly pass-through: content blocks map
directly to TextBlock/ToolCallBlock, and Anthropic already nests tool
results inside one "user" turn (which is exactly what a "tool_results"
normalized turn becomes for this provider).
"""

import anthropic

from providers.base_provider import (
    BaseProvider,
    ImageBlock,
    ProviderError,
    ProviderResponse,
    TextBlock,
    ToolCallBlock,
    ToolResult,
)


class AnthropicProvider(BaseProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, max_tokens: int = 4096):
        self._client = anthropic.Anthropic(api_key=api_key)
        self.model = model
        self.max_tokens = max_tokens

    def send(self, messages: list, tools: list, system: str) -> ProviderResponse:
        wire_messages = [self._to_wire_message(m) for m in messages]
        wire_tools = tools  # already in Anthropic's shape — TOOL_DEFINITIONS is authored that way

        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                messages=wire_messages,
                tools=wire_tools,
            )
        except anthropic.APIError as e:
            raise ProviderError(str(e)) from e

        return ProviderResponse(content=[self._from_wire_block(b) for b in response.content])

    def _to_wire_message(self, message: dict) -> dict:
        role, content = message["role"], message["content"]

        if role == "user" and isinstance(content, str):
            return {"role": "user", "content": content}

        if role == "user" and isinstance(content, list):
            # Multimodal content, e.g. DebuggingAgent's failure-screenshot evidence.
            blocks = []
            for block in content:
                if isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageBlock):
                    blocks.append(
                        {
                            "type": "image",
                            "source": {"type": "base64", "media_type": block.media_type, "data": block.data},
                        }
                    )
            return {"role": "user", "content": blocks}

        if role == "assistant":
            blocks = []
            for block in content:
                if isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ToolCallBlock):
                    blocks.append({"type": "tool_use", "id": block.id, "name": block.name, "input": block.input})
            return {"role": "assistant", "content": blocks}

        if role == "tool_results":
            blocks = [
                {"type": "tool_result", "tool_use_id": r.tool_call_id, "content": r.content} for r in content
            ]
            return {"role": "user", "content": blocks}

        raise ValueError(f"Unrecognized normalized message role: {role}")

    @staticmethod
    def _from_wire_block(block):
        if block.type == "text":
            return TextBlock(text=block.text)
        if block.type == "tool_use":
            return ToolCallBlock(id=block.id, name=block.name, input=block.input)
        raise ValueError(f"Unrecognized Anthropic content block type: {block.type}")
