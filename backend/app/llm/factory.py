"""LLM provider factory with fallback support."""

import logging
from typing import Optional

from app.config import Config, get_config
from app.llm.base import BaseLLMProvider, LLMProviderError
from app.llm.claude import ClaudeProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai import OpenAIProvider

logger = logging.getLogger(__name__)

# Provider registry
PROVIDERS = {
    "ollama": OllamaProvider,
    "claude": ClaudeProvider,
    "openai": OpenAIProvider,
}


async def get_llm_provider(config: Optional[Config] = None) -> BaseLLMProvider:
    """
    Get an LLM provider based on configuration.

    Tries the primary provider first, then falls back through the
    fallback chain if the primary is unavailable.

    Args:
        config: Optional config, uses global config if not provided

    Returns:
        An available LLM provider

    Raises:
        LLMProviderError: If no providers are available
    """
    if config is None:
        config = get_config()

    primary_name = config.llm.provider

    # Validate provider name
    if primary_name not in PROVIDERS:
        raise LLMProviderError(
            f"Unknown LLM provider: {primary_name}. "
            f"Available: {', '.join(PROVIDERS.keys())}"
        )

    # Try primary provider
    primary = PROVIDERS[primary_name](config)
    if await primary.is_available():
        logger.info(f"Using primary LLM provider: {primary_name} ({primary.model_name})")
        return primary

    logger.warning(f"Primary LLM provider '{primary_name}' is not available")

    # Try fallbacks
    for fallback_name in config.llm.fallback_chain:
        if fallback_name not in PROVIDERS:
            logger.warning(f"Unknown fallback provider: {fallback_name}, skipping")
            continue

        fallback = PROVIDERS[fallback_name](config)
        if await fallback.is_available():
            logger.info(
                f"Using fallback LLM provider: {fallback_name} ({fallback.model_name})"
            )
            return fallback

        logger.debug(f"Fallback provider '{fallback_name}' is not available")

    # No providers available
    raise LLMProviderError(
        f"No LLM providers available. Tried: {primary_name}, "
        f"{', '.join(config.llm.fallback_chain)}. "
        "Please ensure Ollama is running or configure API keys."
    )


async def check_all_providers(config: Optional[Config] = None) -> dict[str, dict]:
    """
    Check availability of all configured providers.

    Returns:
        Dict mapping provider name to status info
    """
    if config is None:
        config = get_config()

    results = {}

    for name, provider_class in PROVIDERS.items():
        provider = provider_class(config)
        is_available = await provider.is_available()

        results[name] = {
            "available": is_available,
            "model": provider.model_name,
            "is_primary": name == config.llm.provider,
            "in_fallback_chain": name in config.llm.fallback_chain,
        }

    return results
