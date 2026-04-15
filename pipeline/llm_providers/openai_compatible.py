from __future__ import annotations

import asyncio
from typing import Any, Dict, Optional

from openai import OpenAI

from pipeline.config import LLMConfig

from .base import ProviderResult
from .extractors import extract_completion_text, model_to_dict


class OpenAICompatibleProvider:
    def __init__(self, config: LLMConfig, api_key: Optional[str]) -> None:
        if not config.base_url:
            raise RuntimeError("Provider openai_compatible requires llm.base_url")
        if not config.api_key_env:
            raise RuntimeError("Provider openai_compatible requires llm.api_key_env")
        if not api_key:
            raise RuntimeError(f"Missing API key in env {config.api_key_env}")

        self.config = config
        self.api_key = api_key
        self.endpoint = str(config.options.get("endpoint", "responses"))
        self.client = OpenAI(base_url=config.base_url, api_key=api_key)

    async def generate(self, chunk_id: int, prompt: str) -> ProviderResult:
        try:
            completion = await asyncio.to_thread(self._create_completion, prompt)
            content, text_source = extract_completion_text(completion)
            response_id = getattr(completion, "id", "")
            metadata: Dict[str, Any] = {
                "provider": "openai_compatible",
                "model": self.config.model,
                "request_endpoint": self.endpoint,
                "response_id": response_id,
                "id": response_id,
                "base_url": self.config.base_url,
                "usage": model_to_dict(getattr(completion, "usage", None)) or {},
                "text_source": text_source,
            }
            return ProviderResult(raw_text=content, metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            target = self.config.base_url or "<missing base_url>"
            raise RuntimeError(
                f"Provider openai_compatible failed for chunk {chunk_id}: "
                f"{self.endpoint} model={self.config.model} target={target}: {exc}"
            ) from exc

    def _create_completion(self, prompt: str) -> Any:
        if self.endpoint == "chat_completions":
            return self.client.chat.completions.create(
                model=self.config.model,
                messages=[{"role": "user", "content": prompt}],
            )
        if self.endpoint == "responses":
            return self.client.responses.create(model=self.config.model, input=prompt)
        raise ValueError(f"Unsupported openai_compatible endpoint: {self.endpoint}")

    async def close(self) -> None:
        return None
