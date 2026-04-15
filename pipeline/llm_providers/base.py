from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass
class ProviderResult:
    raw_text: str
    metadata: Dict[str, Any]


class BaseProvider(Protocol):
    async def generate(self, chunk_id: int, prompt: str) -> ProviderResult:
        ...

    async def close(self) -> None:
        ...
