"""LLM client abstraction for the pipeline."""
from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import json

from .config import LLMConfig
from .llm_providers.base import BaseProvider
from .llm_providers.factory import build_provider


@dataclass
class LLMRequest:
    chunk_id: int
    prompt: str


@dataclass
class LLMResponse:
    chunk_id: int
    raw_text: str
    metadata: Dict[str, object]


class LLMClient:
    def __init__(self, config: LLMConfig, cache_dir: Path) -> None:
        self.config = config
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        api_key = os.getenv(self.config.api_key_env) if self.config.api_key_env else None
        self.provider: BaseProvider = build_provider(config, api_key)
        self._preflight_completed = False

    def _cache_path(self, chunk_id: int) -> Path:
        return self.cache_dir / f"chunk_{chunk_id:03}.json"

    def _load_cache(self, chunk_id: int) -> Optional[LLMResponse]:
        cache_file = self._cache_path(chunk_id)
        if cache_file.exists():
            data = json.loads(cache_file.read_text(encoding="utf-8"))
            raw_text = data.get("raw_text", "")
            metadata = data.get("metadata", {})
            usage = metadata.get("usage", {}) if isinstance(metadata, dict) else {}
            if not self._cache_matches_current_config(metadata):
                return None
            if not raw_text and isinstance(usage, dict) and usage.get("completion_tokens", 0) > 0:
                return None
            return LLMResponse(chunk_id=chunk_id, raw_text=raw_text, metadata=metadata)
        return None

    def _cache_matches_current_config(self, metadata: object) -> bool:
        if not isinstance(metadata, dict):
            return False
        cached_provider = metadata.get("provider")
        cached_model = metadata.get("model")
        return cached_provider == self.config.provider and cached_model == self.config.model

    def _save_cache(self, response: LLMResponse) -> None:
        cache_file = self._cache_path(response.chunk_id)
        payload = {"raw_text": response.raw_text, "metadata": response.metadata}
        cache_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    async def _run_preflight(self) -> None:
        if self._preflight_completed:
            return

        prompt = "Return exactly OK"
        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self.provider.generate(0, prompt)
                if not result.raw_text.strip():
                    endpoint = result.metadata.get("request_endpoint", "") if isinstance(result.metadata, dict) else ""
                    raise RuntimeError(
                        f"LLM preflight failed: provider={self.config.provider} model={self.config.model} "
                        f"endpoint={endpoint or '<unknown>'} returned empty text"
                    )
                self._preflight_completed = True
                return
            except Exception:
                if attempt == self.config.max_retries:
                    raise
                await asyncio.sleep(self.config.retry_backoff_seconds * attempt)

    async def send_prompt(self, chunk_id: int, prompt: str) -> LLMResponse:
        cached = self._load_cache(chunk_id)
        if cached:
            return cached

        for attempt in range(1, self.config.max_retries + 1):
            try:
                result = await self.provider.generate(chunk_id, prompt)
                llm_response = LLMResponse(chunk_id=chunk_id, raw_text=result.raw_text, metadata=result.metadata)
                self._save_cache(llm_response)
                return llm_response
            except Exception:  # noqa: BLE001
                if attempt == self.config.max_retries:
                    raise
                await asyncio.sleep(self.config.retry_backoff_seconds * attempt)

        raise RuntimeError("LLM call failed after retries")

    async def send_batch(self, requests: Iterable[LLMRequest]) -> List[LLMResponse]:
        request_list = list(requests)
        if not request_list:
            return []

        await self._run_preflight()

        semaphore = asyncio.Semaphore(self.config.max_concurrency)
        responses: List[LLMResponse] = []

        async def _send(request: LLMRequest) -> None:
            async with semaphore:
                result = await self.send_prompt(request.chunk_id, request.prompt)
                responses.append(result)

        await asyncio.gather(*[_send(req) for req in request_list])
        return sorted(responses, key=lambda r: r.chunk_id)

    async def close(self) -> None:
        await self.provider.close()
