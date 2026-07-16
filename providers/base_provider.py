"""
Base provider interface.

Every LLM provider (Anthropic, OpenAI, DeepSeek, local models) implements
this same interface, so DebuggingAgent and AgentController never contain
provider-specific code — they only ever talk to a BaseProvider.

Two layers, both defined here:

1. `send(messages, tools, system) -> ProviderResponse` — the low-level
   primitive that powers the EXISTING multi-turn, tool-calling loops in
   AgentController and DebuggingAgent (exploring files, deciding what's
   relevant, applying a fix across several turns). Each concrete
   provider translates the NORMALIZED messages/tools given here into
   its own wire format internally — that translation never leaks
   outside providers/.

2. The 5 semantic convenience methods required by the product spec
   (analyze_code, explain_error, suggest_fix, rewrite_code,
   generate_tests) — implemented ONCE, here, on top of `send()`. They
   are single-shot (no tools, no multi-turn exploration) and power
   "Agent Interface Mode"'s structured JSON contract. No provider needs
   to override these; they work for free once `send()` is implemented.

Normalized message format (what callers build and pass to `send()`):
    [
      {"role": "user", "content": "plain text"},
      {"role": "user", "content": [TextBlock(...), ImageBlock(...)]},  # multimodal, e.g. failure screenshots
      {"role": "assistant", "content": [TextBlock(...), ToolCallBlock(...)]},
      {"role": "tool_results", "content": [ToolResult(...), ...]},
    ]

This is intentionally close to Anthropic's own shape (since that's what
the existing, tested code already produces) but is provider-neutral:
OpenAI-compatible providers expand a "tool_results" turn into several
separate {"role": "tool", ...} messages internally; Anthropic keeps
them nested in one "user" turn. Callers never need to know which.
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class TextBlock:
    text: str
    type: str = "text"


@dataclass
class ImageBlock:
    data: str  # base64-encoded image bytes
    media_type: str = "image/png"
    type: str = "image"


@dataclass
class ToolCallBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"


@dataclass
class ToolResult:
    tool_call_id: str
    content: str  # JSON-serialized result, matching the existing convention


@dataclass
class ProviderResponse:
    content: list  # list[TextBlock | ToolCallBlock]


class ProviderError(Exception):
    """Raised for provider-level failures (auth, rate limit, connection).
    Callers (AgentController, TestRepairLoop) already catch broad
    exceptions around LLM calls, so this doesn't require new handling —
    it exists so provider implementations have one clear exception type
    to raise instead of leaking SDK-specific exception classes upward."""


class BaseProvider(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, messages: list, tools: list, system: str) -> ProviderResponse:
        """
        Send a normalized conversation + Anthropic-shaped tool
        definitions (agent/tools/definitions.py's TOOL_DEFINITIONS) to
        this provider's model, translating both into whatever wire
        format the underlying API needs, and return a ProviderResponse
        with normalized content blocks.
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Semantic methods — implemented once, here, for every provider.
    # Single-shot: no tools, no multi-turn exploration. Each expects a
    # JSON object back and parses it; if the model doesn't cooperate,
    # the raw text is returned under "raw_response" so callers can still
    # see what happened rather than getting a silent empty result.
    # ------------------------------------------------------------------

    def analyze_code(self, code: str, language: Optional[str] = None) -> dict:
        system = (
            "You are a code analysis assistant. Analyze the given code for bugs, "
            "security issues, and quality problems. Respond with ONLY a JSON object "
            'shaped like: {"issues_found": [string, ...], "severity": "none|low|medium|high|critical", '
            '"explanation": string}. No prose outside the JSON.'
        )
        prompt = f"Language: {language or 'unspecified'}\n\nCode:\n{code}"
        return self._single_shot_json(system, prompt)

    def explain_error(self, code: str, error_message: str, language: Optional[str] = None) -> dict:
        system = (
            "You are a debugging assistant. Given code and an error/stack trace, "
            "explain the root cause in plain language. Respond with ONLY a JSON "
            'object shaped like: {"explanation": string, "root_cause_file_hint": string, '
            '"severity": "low|medium|high|critical"}. No prose outside the JSON.'
        )
        prompt = f"Language: {language or 'unspecified'}\n\nCode:\n{code}\n\nError:\n{error_message}"
        return self._single_shot_json(system, prompt)

    def suggest_fix(self, code: str, issue_description: str, language: Optional[str] = None) -> dict:
        system = (
            "You are a debugging assistant. Given code and a description of what's "
            "wrong, describe a targeted fix WITHOUT rewriting the whole file. "
            'Respond with ONLY a JSON object shaped like: {"suggested_fix": string, '
            '"confidence": "low|medium|high"}. No prose outside the JSON.'
        )
        prompt = f"Language: {language or 'unspecified'}\n\nCode:\n{code}\n\nIssue:\n{issue_description}"
        return self._single_shot_json(system, prompt)

    def rewrite_code(self, code: str, fix_description: str, language: Optional[str] = None) -> dict:
        system = (
            "You are a debugging assistant. Rewrite the given code to apply the "
            "described fix, changing as little as possible beyond what's needed. "
            'Respond with ONLY a JSON object shaped like: {"rewritten_code": string, '
            '"explanation": string}. No prose outside the JSON, no markdown code fences '
            "inside the rewritten_code string."
        )
        prompt = f"Language: {language or 'unspecified'}\n\nOriginal code:\n{code}\n\nFix to apply:\n{fix_description}"
        return self._single_shot_json(system, prompt)

    def generate_tests(self, code: str, language: Optional[str] = None) -> dict:
        system = (
            "You are a test-writing assistant. Generate test cases for the given "
            'code. Respond with ONLY a JSON object shaped like: {"tests_generated": '
            '[string, ...]} where each string is a complete, runnable test case in '
            "the same language as the code. No prose outside the JSON."
        )
        prompt = f"Language: {language or 'unspecified'}\n\nCode:\n{code}"
        return self._single_shot_json(system, prompt)

    # ------------------------------------------------------------------
    # Shared helper
    # ------------------------------------------------------------------

    def _single_shot_json(self, system: str, user_content: str) -> dict:
        messages = [{"role": "user", "content": user_content}]
        response = self.send(messages, tools=[], system=system)

        text = "\n".join(block.text for block in response.content if isinstance(block, TextBlock))
        try:
            return json.loads(_extract_json(text))
        except (json.JSONDecodeError, ValueError):
            return {"raw_response": text, "parse_error": True}


def _extract_json(text: str) -> str:
    """Models occasionally wrap JSON in markdown fences despite
    instructions not to — strip those before parsing rather than
    failing on an easily-recoverable formatting quirk."""
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        stripped = "\n".join(lines)
    return stripped
