"""
Shared OpenAI-compatible provider implementation.

DeepSeek's API is documented as OpenAI-SDK-compatible (same `openai`
Python package, just a different base_url and model names), and most
local model servers (e.g. Ollama) expose an OpenAI-compatible endpoint
too. Rather than writing three near-identical providers, this one
implementation handles the actual wire-format translation, and
OpenAIProvider / DeepSeekProvider / LocalProvider are thin subclasses
that just set base_url, default model, and which env var holds the key.

Translation notes (this is the real difference from Anthropic's shape):
  - Tool schemas: Anthropic's {"name", "description", "input_schema"}
    becomes OpenAI's {"type": "function", "function": {"name",
    "description", "parameters"}} — same JSON Schema, different wrapper.
  - Assistant turns: OpenAI wants ONE message with an optional `content`
    string plus a separate `tool_calls` array — not nested content
    blocks like Anthropic.
  - Tool results: OpenAI wants ONE SEPARATE MESSAGE PER RESULT
    ({"role": "tool", "tool_call_id", "content"}), not one turn
    containing several results like Anthropic.
"""

import json

from openai import OpenAI
from openai import APIError as OpenAIAPIError

from providers.base_provider import BaseProvider, ImageBlock, ProviderError, ProviderResponse, TextBlock, ToolCallBlock


class OpenAICompatibleProvider(BaseProvider):
    def __init__(self, api_key: str, model: str, base_url: str = None, max_tokens: int = 4096):
        self._client = OpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.max_tokens = max_tokens

    def send(self, messages: list, tools: list, system: str) -> ProviderResponse:
        wire_messages = [{"role": "system", "content": system}]
        for message in messages:
            wire_messages.extend(self._to_wire_messages(message))

        wire_tools = [self._to_wire_tool(t) for t in tools] if tools else None

        try:
            response = self._client.chat.completions.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=wire_messages,
                tools=wire_tools,
            )
        except OpenAIAPIError as e:
            raise ProviderError(str(e)) from e

        return ProviderResponse(content=self._from_wire_message(response.choices[0].message))

    def _to_wire_messages(self, message: dict) -> list:
        role, content = message["role"], message["content"]

        if role == "user" and isinstance(content, str):
            return [{"role": "user", "content": content}]

        if role == "user" and isinstance(content, list):
            # Multimodal content, e.g. DebuggingAgent's failure-screenshot evidence.
            # NOTE: whether this actually does anything useful depends on the
            # configured model supporting image input — not all OpenAI-compatible
            # backends (e.g. some DeepSeek/local text-only models) do. Untested
            # against a real vision-capable non-Anthropic model in this environment.
            blocks = []
            for block in content:
                if isinstance(block, TextBlock):
                    blocks.append({"type": "text", "text": block.text})
                elif isinstance(block, ImageBlock):
                    blocks.append(
                        {"type": "image_url", "image_url": {"url": f"data:{block.media_type};base64,{block.data}"}}
                    )
            return [{"role": "user", "content": blocks}]

        if role == "assistant":
            text_parts = [b.text for b in content if isinstance(b, TextBlock)]
            tool_calls = [
                {
                    "id": b.id,
                    "type": "function",
                    "function": {"name": b.name, "arguments": json.dumps(b.input)},
                }
                for b in content
                if isinstance(b, ToolCallBlock)
            ]
            wire_msg = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tool_calls:
                wire_msg["tool_calls"] = tool_calls
            return [wire_msg]

        if role == "tool_results":
            # Each result becomes its OWN message — this is the one place
            # a single normalized turn expands into several wire messages.
            return [{"role": "tool", "tool_call_id": r.tool_call_id, "content": r.content} for r in content]

        raise ValueError(f"Unrecognized normalized message role: {role}")

    @staticmethod
    def _to_wire_tool(tool: dict) -> dict:
        # Translates FROM agent/tools/definitions.py's Anthropic-shaped
        # TOOL_DEFINITIONS — that file stays the single source of truth
        # and never needs to know OpenAI-shaped tools exist.
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["input_schema"],
            },
        }

    @staticmethod
    def _from_wire_message(message) -> list:
        blocks = []
        if message.content:
            blocks.append(TextBlock(text=message.content))
        if message.tool_calls:
            for call in message.tool_calls:
                blocks.append(
                    ToolCallBlock(
                        id=call.id,
                        name=call.function.name,
                        input=json.loads(call.function.arguments),
                    )
                )
        return blocks
