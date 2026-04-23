"""Configuration models and loader for the automation pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional

import json

DEFAULT_CONFIG_PATH = Path("pipeline_config.json")


@dataclass
class PathsConfig:
    docx: Path
    artifacts_dir: Path
    prompt_cache_dir: Path
    responses_dir: Path
    output_excel: Path


@dataclass
class LLMConfig:
    model: str
    api_key_env: Optional[str] = "OPENAI_API_KEY"
    base_url: Optional[str] = None
    provider: str = "openai_compatible"
    headers: Dict[str, str] = field(default_factory=dict)
    options: Dict[str, Any] = field(default_factory=dict)
    timeout_seconds: int = 120
    max_concurrency: int = 1
    max_retries: int = 3
    retry_backoff_seconds: int = 5


@dataclass
class BatchConfig:
    batch_size: int = 5


@dataclass
class ExecutionFlags:
    resume: bool = False
    dry_run: bool = False
    preview: bool = False
    skip_llm: bool = False


@dataclass
class OutputConfig:
    version_prefix: str = "未知版本"
    assignee: str = "liwenqiu"
    prompt_context: str = ""


@dataclass
class PipelineConfig:
    paths: PathsConfig
    llm: LLMConfig
    batch: BatchConfig
    flags: ExecutionFlags
    output: OutputConfig = field(default_factory=OutputConfig)

    @classmethod
    def from_dict(cls, payload: Dict[str, Any], root: Optional[Path] = None) -> "PipelineConfig":
        root = root or Path.cwd()
        paths_payload = payload.get("paths", {})
        llm_payload = payload.get("llm", {})
        batch_payload = payload.get("batch", {})
        flags_payload = payload.get("flags", {})
        output_payload = payload.get("output", {})

        artifacts_dir_rel = Path(paths_payload.get("artifacts_dir", "artifacts"))
        responses_dir_rel = Path(paths_payload.get("responses_dir", str(artifacts_dir_rel / "responses")))

        paths = PathsConfig(
            docx=root / paths_payload.get("docx", "source/wordv1.3.7.docx"),
            artifacts_dir=root / artifacts_dir_rel,
            prompt_cache_dir=root / paths_payload.get("prompt_cache_dir", "prompt_cache"),
            responses_dir=root / responses_dir_rel,
            output_excel=root / paths_payload.get("output_excel", "output/output_test_cases.xlsx"),
        )

        provider = str(llm_payload.get("provider", "openai_compatible")).strip() or "openai_compatible"
        options = dict(llm_payload.get("options", {}))
        base_url = llm_payload.get("base_url")
        model = llm_payload.get("model")

        if provider == "openai_compatible":
            options.setdefault("endpoint", "responses")
            if not base_url:
                raise ValueError("Config llm.base_url is required for openai_compatible")
            if not model:
                raise ValueError("Config llm.model is required for openai_compatible")

        llm = LLMConfig(
            provider=provider,
            base_url=base_url,
            model=str(model or "gpt-5-codex"),
            api_key_env=llm_payload.get("api_key_env", "OPENAI_API_KEY"),
            headers=dict(llm_payload.get("headers", {})),
            options=options,
            timeout_seconds=int(llm_payload.get("timeout_seconds", 120)),
            max_concurrency=int(llm_payload.get("max_concurrency", 1)),
            max_retries=int(llm_payload.get("max_retries", 3)),
            retry_backoff_seconds=int(llm_payload.get("retry_backoff_seconds", 5)),
        )

        batch = BatchConfig(batch_size=int(batch_payload.get("batch_size", 5)))

        flags = ExecutionFlags(
            resume=bool(flags_payload.get("resume", False)),
            dry_run=bool(flags_payload.get("dry_run", False)),
            preview=bool(flags_payload.get("preview", False)),
            skip_llm=bool(flags_payload.get("skip_llm", False)),
        )

        output = OutputConfig(
            version_prefix=str(output_payload.get("version_prefix", "未知版本")),
            assignee=str(output_payload.get("assignee", "liwenqiu")),
            prompt_context=str(output_payload.get("prompt_context", "")),
        )

        return cls(paths=paths, llm=llm, batch=batch, flags=flags, output=output)


def load_config(config_path: Optional[Path] = None) -> PipelineConfig:
    path = config_path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    payload = json.loads(path.read_text(encoding="utf-8"))
    return PipelineConfig.from_dict(payload, root=path.parent)
