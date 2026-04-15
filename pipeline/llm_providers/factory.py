from __future__ import annotations

from typing import Optional

from pipeline.config import LLMConfig

from .anthropic_provider import AnthropicProvider
from .base import BaseProvider
from .custom_http import CustomHTTPProvider
from .openai_compatible import OpenAICompatibleProvider


def build_provider(config: LLMConfig, api_key: Optional[str]) -> BaseProvider:
    provider = (config.provider or "openai_compatible").strip().lower()
    if provider == "openai_compatible":
        return OpenAICompatibleProvider(config, api_key)
    if provider == "custom_http":
        return CustomHTTPProvider(config, api_key)
    if provider == "anthropic":
        return AnthropicProvider(config, api_key)
    raise ValueError(f"Unsupported LLM provider: {config.provider}")
