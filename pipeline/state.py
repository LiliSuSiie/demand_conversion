"""State persistence for pipeline stages."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import json

STATE_FILENAME = "pipeline_state.json"


@dataclass
class StageMetadata:
    name: str
    completed: bool
    timestamp: str
    details: Dict[str, object] = field(default_factory=dict)


class PipelineState:
    def __init__(self, artifacts_dir: Path) -> None:
        self.artifacts_dir = artifacts_dir
        self.state_path = artifacts_dir / STATE_FILENAME
        self._stages: Dict[str, StageMetadata] = {}
        if self.state_path.exists():
            self._load()

    def _load(self) -> None:
        data = json.loads(self.state_path.read_text(encoding="utf-8"))
        for entry in data.get("stages", []):
            self._stages[entry["name"]] = StageMetadata(
                name=entry["name"],
                completed=entry.get("completed", False),
                timestamp=entry.get("timestamp", ""),
                details=entry.get("details", {}),
            )

    def _save(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "stages": [
                {
                    "name": meta.name,
                    "completed": meta.completed,
                    "timestamp": meta.timestamp,
                    "details": meta.details,
                }
                for meta in self._stages.values()
            ]
        }
        self.state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def stage_completed(self, name: str) -> bool:
        meta = self._stages.get(name)
        return bool(meta and meta.completed)

    def record_stage(self, name: str, details: Optional[Dict[str, object]] = None) -> None:
        meta = StageMetadata(
            name=name,
            completed=True,
            timestamp=datetime.utcnow().isoformat() + "Z",
            details=details or {},
        )
        self._stages[name] = meta
        self._save()

    def reset_stage(self, name: str) -> None:
        if name in self._stages:
            del self._stages[name]
            self._save()

    def reset_all(self) -> None:
        self._stages.clear()
        if self.state_path.exists():
            self.state_path.unlink()

    def as_dict(self) -> Dict[str, StageMetadata]:
        return self._stages.copy()
