"""LLM provider factory for Groq engine."""

from app.services.llm.base import BaseLLMProvider, LLMResponse
from app.services.llm.groq_provider import GroqProvider
from app.config import settings


# Registry of available LLM providers
PROVIDER_MAP: dict[str, type[BaseLLMProvider]] = {
    "groq": GroqProvider,
}


def get_provider(name: str = "groq") -> BaseLLMProvider:
    """Create and return an LLM provider instance.

    Args:
        name: Provider name (defaults to 'groq').

    Returns:
        Instantiated Groq provider.

    Raises:
        ValueError: If provider is unknown or GROQ_API_KEY is missing.
    """
    return GroqProvider()


def get_available_providers() -> list[str]:
    """Get list of provider names that have API keys configured.

    Returns:
        List of available provider name strings.
    """
    if settings.groq_api_key:
        return ["groq"]
    return []
