from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module


@dataclass
class ProviderConfig:
    """Configuration for a live chat model; keys are optional offline."""

    provider: str
    model_name: str
    temperature: float
    api_key: str | None = None
    base_url: str | None = None


def normalize_provider(value: str) -> str:
    """Return a canonical provider name or report unsupported input."""
    aliases = {
        "openai": "openai", "custom": "custom", "openai-compatible": "custom",
        "gemini": "gemini", "google": "gemini", "google-genai": "gemini",
        "anthropic": "anthropic", "anthorpic": "anthropic", "claude": "anthropic",
        "ollama": "ollama", "openrouter": "openrouter", "open-router": "openrouter",
    }
    key = value.strip().lower().replace("_", "-")
    if key not in aliases:
        raise ValueError(f"Unknown provider {value!r}. Supported: openai, custom, gemini, anthropic, ollama, openrouter.")
    return aliases[key]


def build_chat_model(config: ProviderConfig):
    """Construct a live model lazily; no API request is made here."""
    provider = normalize_provider(config.provider)
    if provider == "custom" and not config.base_url:
        raise ValueError("custom provider requires CUSTOM_BASE_URL or LLM_BASE_URL.")
    integrations = {
        "openai": ("langchain_openai", "ChatOpenAI"),
        "custom": ("langchain_openai", "ChatOpenAI"),
        "gemini": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
        "anthropic": ("langchain_anthropic", "ChatAnthropic"),
        "ollama": ("langchain_ollama", "ChatOllama"),
        "openrouter": ("langchain_openrouter", "ChatOpenRouter"),
    }
    module_name, class_name = integrations[provider]
    try:
        model_class = getattr(import_module(module_name), class_name)
    except ImportError as exc:
        package = module_name.replace("_", "-")
        raise ImportError(f"Live provider {provider!r} requires {package}: pip install {package}") from exc
    kwargs = {"model": config.model_name, "temperature": config.temperature}
    if provider != "ollama" and config.api_key:
        kwargs["api_key"] = config.api_key
    elif provider == "custom":
        # Local compatible endpoints may not authenticate; the SDK needs a value.
        kwargs["api_key"] = "not-required"
    if config.base_url:
        if provider == "gemini":
            kwargs["client_options"] = {"api_endpoint": config.base_url}
        else:
            kwargs["base_url"] = config.base_url
    return model_class(**kwargs)
