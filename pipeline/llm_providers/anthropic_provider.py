from __future__ import annotations

from typing import Optional

from pipeline.config import LLMConfig

from .base import ProviderResult


class AnthropicProvider:
    def __init__(self, config: LLMConfig, api_key: Optional[str]) -> None:
        self.config = config
        self.api_key = api_key

    async def generate(self, chunk_id: int, prompt: str) -> ProviderResult:
        raise NotImplementedError(
            "Provider anthropic is reserved but not implemented yet. "
            f"chunk={chunk_id} model={self.config.model}"
        )

    async def close(self) -> None:
        return None
