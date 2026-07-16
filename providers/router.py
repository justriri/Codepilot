"""
Provider router.

Constructs the configured provider so nothing else in the codebase
hardcodes a specific one. `DEFAULT_MODEL` in .env selects which
provider is active; the user switches providers by changing that one
value, never agent logic.
"""

from providers.anthropic_provider import AnthropicProvider
from providers.deepseek_provider import DeepSeekProvider
from providers.local_provider import LocalProvider
from providers.openai_provider import OpenAIProvider


def get_provider(config):
    """config is an AgentConfig (agent/config.py)."""
    provider_name = config.default_model_provider.lower()

    if provider_name == "anthropic":
        if not config.anthropic_api_key:
            raise RuntimeError("DEFAULT_MODEL=anthropic requires ANTHROPIC_API_KEY to be set in .env.")
        return AnthropicProvider(api_key=config.anthropic_api_key, model=config.anthropic_model)

    if provider_name == "deepseek":
        if not config.deepseek_api_key:
            raise RuntimeError("DEFAULT_MODEL=deepseek requires DEEPSEEK_API_KEY to be set in .env.")
        return DeepSeekProvider(api_key=config.deepseek_api_key, model=config.deepseek_model)

    if provider_name == "openai":
        if not config.openai_api_key:
            raise RuntimeError("DEFAULT_MODEL=openai requires OPENAI_API_KEY to be set in .env.")
        return OpenAIProvider(api_key=config.openai_api_key, model=config.openai_model)

    if provider_name == "local":
        return LocalProvider(
            model=config.local_model_name, base_url=config.local_model_base_url
        )

    raise RuntimeError(
        f"Unknown DEFAULT_MODEL provider: '{provider_name}'. "
        "Expected one of: anthropic, deepseek, openai, local."
    )
