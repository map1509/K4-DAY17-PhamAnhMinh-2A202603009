from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
from model_provider import ProviderConfig, normalize_provider

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini", "custom": "local-model",
    "gemini": "gemini-2.5-flash", "anthropic": "claude-sonnet-4-5",
    "ollama": "llama3.2", "openrouter": "openai/gpt-4o-mini",
}


@dataclass
class LabConfig:
    """Shared paths, compaction settings, and model configuration."""

    base_dir: Path = REPO_ROOT
    data_dir: Path = REPO_ROOT / "data"
    state_dir: Path = REPO_ROOT / "state"
    compact_threshold_tokens: int = 2000
    compact_keep_messages: int = 4
    model: ProviderConfig = field(default_factory=lambda: ProviderConfig("openai", "gpt-4o-mini", 0.0))
    judge_model: ProviderConfig = field(default_factory=lambda: ProviderConfig("openai", "gpt-4o-mini", 0.0))


def _positive_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer.") from exc
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer.")
    return value


def _provider_config(prefix: str, fallback: ProviderConfig | None = None) -> ProviderConfig:
    provider = normalize_provider(os.getenv(f"{prefix}_PROVIDER", fallback.provider if fallback else "openai"))
    same_provider = fallback is not None and provider == fallback.provider
    model_name = os.getenv(f"{prefix}_MODEL", fallback.model_name if same_provider else DEFAULT_MODELS[provider]).strip()
    if not model_name:
        raise ValueError(f"{prefix}_MODEL must not be empty.")
    try:
        temperature = float(os.getenv(f"{prefix}_TEMPERATURE", str(fallback.temperature if fallback else 0.0)))
    except ValueError as exc:
        raise ValueError(f"{prefix}_TEMPERATURE must be a finite number.") from exc
    if not math.isfinite(temperature) or temperature < 0:
        raise ValueError(f"{prefix}_TEMPERATURE must be finite and non-negative.")
    provider_key = os.getenv(f"{provider.upper()}_API_KEY")
    if provider == "gemini":
        provider_key = provider_key or os.getenv("GOOGLE_API_KEY")
    api_key = os.getenv(f"{prefix}_API_KEY") or provider_key or (fallback.api_key if same_provider else None)
    base_url = os.getenv(f"{prefix}_BASE_URL") or os.getenv(f"{provider.upper()}_BASE_URL") or (fallback.base_url if same_provider else None)
    if provider == "ollama" and not base_url:
        base_url = "http://localhost:11434"
    return ProviderConfig(provider, model_name, temperature, api_key, base_url)


def load_config(base_dir: Path | None = None) -> LabConfig:
    """Read root/.env without overriding environment; no SDK or API key needed."""
    root = (base_dir or REPO_ROOT).resolve()
    load_dotenv(root / ".env", override=False, encoding="utf-8")
    model = _provider_config("LLM")
    judge_model = _provider_config("JUDGE", model)
    threshold = _positive_int("COMPACT_THRESHOLD_TOKENS", 2000)
    keep_messages = _positive_int("COMPACT_KEEP_MESSAGES", 4)
    state_dir = root / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    return LabConfig(root, root / "data", state_dir, threshold, keep_messages, model, judge_model)
