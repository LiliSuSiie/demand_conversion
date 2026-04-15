"""Data structures for parsed requirement blocks."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class RequirementBlock:
    """Standardized representation of a single requirement entry."""

    module: str
    title: str
    description: str
    notes: Optional[str] = None
    block_id: Optional[str] = None
    table_index: Optional[int] = None
    row_index: Optional[int] = None
    segments: Optional[List[str]] = field(default=None)

    def normalize(self) -> "RequirementBlock":
        """Return a copy with trimmed whitespace for all textual fields."""

        normalized_notes = _normalize_multiline(self.notes) if self.notes else ""
        normalized_segments = _normalize_segments(self.segments)
        return RequirementBlock(
            module=_normalize_inline(self.module),
            title=_normalize_inline(self.title),
            description=_normalize_multiline(self.description),
            notes=normalized_notes or None,
            block_id=self.block_id,
            table_index=self.table_index,
            row_index=self.row_index,
            segments=normalized_segments,
        )

    def as_dict(self) -> dict:
        """Serialize to a JSON-friendly dictionary."""

        payload = {
            "module": self.module,
            "title": self.title,
            "description": self.description,
        }
        if self.notes:
            payload["notes"] = self.notes
        if self.block_id:
            payload["block_id"] = self.block_id
        if self.table_index is not None:
            payload["table_index"] = self.table_index
        if self.row_index is not None:
            payload["row_index"] = self.row_index
        if self.segments:
            payload["segments"] = self.segments
        return payload

    def to_prompt_payload(self) -> dict:
        """Return a prompt-friendly dictionary including metadata."""

        payload = self.as_dict()
        payload.setdefault("summary", self.description[:200])
        return payload


def normalize_block(block: RequirementBlock) -> RequirementBlock:
    """Helper for callers that prefer a function over the instance method."""

    return block.normalize()


def _normalize_inline(value: str) -> str:
    return " ".join(value.split())


def _normalize_multiline(value: Optional[str]) -> str:
    if not value:
        return ""

    normalized = (
        value.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\xa0", " ")
        .strip()
    )
    lines = [line.strip() for line in normalized.split("\n")]

    collapsed = []
    previous_blank = True
    for line in lines:
        if not line:
            if collapsed and not previous_blank:
                collapsed.append("")
            previous_blank = True
            continue

        collapsed.append(line)
        previous_blank = False

    return "\n".join(collapsed).strip()


def _normalize_segments(segments: Optional[List[str]]) -> Optional[List[str]]:
    if not segments:
        return None
    normalized = [_normalize_multiline(segment) for segment in segments if segment]
    return normalized or None
