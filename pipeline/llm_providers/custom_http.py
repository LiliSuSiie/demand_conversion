from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, Optional
from urllib import error, request

from pipeline.config import LLMConfig

from .base import ProviderResult
from .extractors import extract_text_from_content, get_by_path


class CustomHTTPProvider:
    def __init__(self, config: LLMConfig, api_key: Optional[str]) -> None:
        if not config.base_url:
            raise RuntimeError("Provider custom_http requires llm.base_url")
        self.config = config
        self.api_key = api_key
        self.method = str(config.options.get("method", "POST")).upper()
        self.path = str(config.options.get("path", ""))
        self.request_format = str(config.options.get("request_format", "prompt_model"))
        self.response_text_path = str(config.options.get("response_text_path", "text"))
        self.response_usage_path = str(config.options.get("response_usage_path", ""))

    async def generate(self, chunk_id: int, prompt: str) -> ProviderResult:
        try:
            status_code, payload = await asyncio.to_thread(self._perform_request, prompt)
            text_value = get_by_path(payload, self.response_text_path)
            raw_text = extract_text_from_content(text_value)
            usage = get_by_path(payload, self.response_usage_path) if self.response_usage_path else {}
            response_id = payload.get("id", "") if isinstance(payload, dict) else ""
            metadata: Dict[str, Any] = {
                "provider": "custom_http",
                "model": self.config.model,
                "request_endpoint": self.path or "/",
                "response_id": response_id,
                "id": response_id,
                "base_url": self.config.base_url,
                "status_code": status_code,
                "usage": usage if isinstance(usage, dict) else {},
                "text_source": self.response_text_path,
            }
            return ProviderResult(raw_text=raw_text, metadata=metadata)
        except Exception as exc:  # noqa: BLE001
            target = self._build_url()
            raise RuntimeError(
                f"Provider custom_http failed for chunk {chunk_id}: "
                f"{self.method} {target} model={self.config.model}: {exc}"
            ) from exc

    def _perform_request(self, prompt: str) -> tuple[int, Any]:
        body = self._build_request_body(prompt)
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = self._build_headers()
        req = request.Request(self._build_url(), data=payload, headers=headers, method=self.method)
        try:
            with request.urlopen(req, timeout=self.config.timeout_seconds) as response:
                status_code = getattr(response, "status", response.getcode())
                charset = response.headers.get_content_charset("utf-8")
                text = response.read().decode(charset)
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"returned {exc.code}: {body_text}") from exc
        parsed = json.loads(text)
        return status_code, parsed

    def _build_request_body(self, prompt: str) -> Dict[str, Any]:
        if self.request_format == "prompt_only":
            return {"prompt": prompt}
        if self.request_format == "prompt_model":
            return {"model": self.config.model, "prompt": prompt}
        if self.request_format == "messages_model":
            return {
                "model": self.config.model,
                "messages": [{"role": "user", "content": prompt}],
            }
        raise ValueError(f"Unsupported custom_http request_format: {self.request_format}")

    def _build_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        for key, value in self.config.headers.items():
            rendered = str(value)
            if "${API_KEY}" in rendered:
                rendered = rendered.replace("${API_KEY}", self.api_key or "")
            headers[str(key)] = rendered
        return headers

    def _build_url(self) -> str:
        base_url = (self.config.base_url or "").rstrip("/")
        if not self.path:
            return base_url
        return f"{base_url}/{self.path.lstrip('/')}"

    async def close(self) -> None:
        return None
