"""Pipeline stage helpers for requirement parsing, prompt generation, and Excel export."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Iterable, List, Optional

from case_models import TestCase
from parser_common import cases_to_dataframe_rows, serialize_to_convert_format
from requirement_models import RequirementBlock

from .config import PipelineConfig
from .llm_client import LLMClient, LLMRequest
from .state import PipelineState
from generate_requirement_prompts import PromptGenerator, LLMOutputParser
import pandas as pd
import json


logger = logging.getLogger(__name__)


def _parse_requirement_tables(docx_path: Path) -> List[RequirementBlock]:
    from requirement_parser import parse_requirement_tables

    return parse_requirement_tables(docx_path)


def _write_preview_file(
    docx_path: Path,
    preview_path: Path,
    blocks: List[RequirementBlock],
    *,
    block_limit: int,
    paragraph_limit: int,
    encoding: str,
    format: str,
) -> None:
    from requirement_extractor import _write_preview

    _write_preview(
        docx_path,
        preview_path,
        blocks,
        block_limit=block_limit,
        paragraph_limit=paragraph_limit,
        encoding=encoding,
        format=format,
    )


class PipelineStages:
    def __init__(self, config: PipelineConfig, state: PipelineState) -> None:
        self.config = config
        self.state = state
        self.artifacts = config.paths.artifacts_dir

    def parse_requirements(self) -> List[RequirementBlock]:
        blocks = _parse_requirement_tables(self.config.paths.docx)
        payload = json.dumps([block.as_dict() for block in blocks], ensure_ascii=False, indent=2)
        self.artifacts.mkdir(parents=True, exist_ok=True)
        requirements_json = self.artifacts / "requirements.json"
        requirements_json.write_text(payload, encoding="utf-8")

        if self.config.flags.preview:
            preview_path = self.artifacts / "requirements_preview.md"
            _write_preview_file(
                self.config.paths.docx,
                preview_path,
                blocks,
                block_limit=10,
                paragraph_limit=8,
                encoding="utf-8",
                format="pretty",
            )

        self.state.record_stage("requirements", {"count": len(blocks)})
        return blocks

    def generate_prompts(self, blocks: List[RequirementBlock]) -> List[str]:
        generator = PromptGenerator(blocks)
        chunks = generator.chunk(self.config.batch.batch_size)
        chunk_dir = self.artifacts / "prompt_chunks"
        chunk_dir.mkdir(parents=True, exist_ok=True)
        rendered_chunks: List[str] = []
        for chunk in chunks:
            content = chunk.render()
            chunk_path = chunk_dir / f"chunk_{chunk.index:03}.txt"
            chunk_path.write_text(content, encoding="utf-8")
            rendered_chunks.append(content)

        self.state.record_stage("prompts", {"count": len(rendered_chunks)})
        return rendered_chunks

    async def call_llm(self, prompts: List[str]) -> List[str]:
        if self.config.flags.dry_run or self.config.flags.skip_llm:
            logger.info(
                "Skipping LLM stage (dry_run=%s skip_llm=%s)",
                self.config.flags.dry_run,
                self.config.flags.skip_llm,
            )
            return []

        client = LLMClient(self.config.llm, self.config.paths.prompt_cache_dir)
        requests = [LLMRequest(chunk_id=idx + 1, prompt=prompt) for idx, prompt in enumerate(prompts)]
        responses = await client.send_batch(requests)
        await client.close()
        response_dir = self.config.paths.responses_dir
        response_dir.mkdir(parents=True, exist_ok=True)
        for response in responses:
            response_path = response_dir / f"chunk_{response.chunk_id:03}.txt"
            response_path.write_text(response.raw_text, encoding="utf-8")

        self.state.record_stage("llm", {"count": len(responses)})
        return [response.raw_text for response in responses]

    def parse_cases(self, responses: List[str]) -> List[TestCase]:
        cases: List[TestCase] = []
        for text in responses:
            parser = LLMOutputParser(text)
            cases.extend(parser.parse())

        cases_payload = {
            "cases": [case.normalize().__dict__ for case in cases],
            "total": len(cases),
        }

        parsed_json = self.artifacts / "parsed_cases.json"
        parsed_json.write_text(json.dumps(cases_payload, ensure_ascii=False, indent=2), encoding="utf-8")

        self.state.record_stage("cases", {"count": len(cases)})
        return cases

    def export_excel(self, cases: Iterable[TestCase]) -> None:
        if self.config.flags.dry_run:
            logger.info("Skipping Excel export because dry_run is enabled")
            return

        rows = cases_to_dataframe_rows(cases)
        if rows:
            print(
                "Writing %d rows to %s" % (len(rows), self.config.paths.output_excel)
            )
            for idx, row in enumerate(rows, 1):
                print(f"[Row {idx}] {json.dumps(row, ensure_ascii=False)}")
        else:
            print("No rows to write to Excel (cases list is empty)")
        df = pd.DataFrame(rows)
        output_path = self.config.paths.output_excel
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Sheet1", index=False)

        convert_txt_path = self.artifacts / "convert.txt"
        convert_txt_path.write_text(serialize_to_convert_format(cases), encoding="utf-8")

        self.state.record_stage("excel", {"rows": len(rows)})

    def load_requirements(self) -> Optional[List[RequirementBlock]]:
        requirements_json = self.artifacts / "requirements.json"
        if not requirements_json.exists():
            return None
        data = json.loads(requirements_json.read_text(encoding="utf-8"))
        return [RequirementBlock(**item) for item in data]

    def load_prompts(self) -> Optional[List[str]]:
        chunk_dir = self.artifacts / "prompt_chunks"
        if not chunk_dir.exists():
            return None
        paths = sorted(chunk_dir.glob("chunk_*.txt"))
        if not paths:
            return None
        return [path.read_text(encoding="utf-8") for path in paths]

    def load_responses(self) -> Optional[List[str]]:
        response_dir = self.config.paths.responses_dir
        if not response_dir.exists():
            return None
        paths = sorted(response_dir.glob("chunk_*.txt"))
        if not paths:
            return None

        responses: List[str] = []
        for path in paths:
            text = path.read_text(encoding="utf-8")
            if not text.strip():
                cache_path = self.config.paths.prompt_cache_dir / path.with_suffix(".json").name
                if cache_path.exists():
                    cache_payload = json.loads(cache_path.read_text(encoding="utf-8"))
                    usage = cache_payload.get("metadata", {}).get("usage", {})
                    if usage.get("completion_tokens", 0) > 0:
                        return None
            responses.append(text)
        return responses

    def load_cases(self) -> Optional[List[TestCase]]:
        parsed_json = self.artifacts / "parsed_cases.json"
        if not parsed_json.exists():
            return None
        data = json.loads(parsed_json.read_text(encoding="utf-8"))
        return [TestCase(**item) for item in data.get("cases", [])]


async def run_pipeline(config: PipelineConfig, state: PipelineState) -> None:
    stages = PipelineStages(config, state)

    def should_resume(name: str) -> bool:
        return config.flags.resume and state.stage_completed(name)

    blocks: List[RequirementBlock]
    if should_resume("requirements"):
        logger.info("Skipping requirements stage (resume enabled)")
        loaded = stages.load_requirements()
        if loaded is None:
            logger.warning("Resume requested but requirements artifacts missing; re-running stage")
            blocks = stages.parse_requirements()
        else:
            blocks = loaded
    else:
        logger.info("Running requirements stage")
        blocks = stages.parse_requirements()

    prompts: List[str]
    if should_resume("prompts"):
        logger.info("Skipping prompt generation stage (resume enabled)")
        loaded = stages.load_prompts()
        if loaded is None:
            logger.warning("Prompt artifacts missing; re-running stage")
            prompts = stages.generate_prompts(blocks)
        else:
            prompts = loaded
    else:
        logger.info("Running prompt generation stage")
        prompts = stages.generate_prompts(blocks)

    responses: List[str]
    if config.flags.dry_run:
        logger.info("Dry-run enabled; skipping LLM stage")
        cached = stages.load_responses()
        if cached:
            logger.info("Using cached LLM responses (%d files)", len(cached))
            responses = cached
        else:
            responses = []
    elif should_resume("llm"):
        logger.info("Skipping LLM stage (resume enabled)")
        loaded = stages.load_responses()
        if loaded is None:
            logger.warning("LLM artifacts missing; re-running stage")
            responses = await stages.call_llm(prompts)
        else:
            responses = loaded
    else:
        logger.info("Running LLM stage")
        responses = await stages.call_llm(prompts)

    cases: List[TestCase]
    if config.flags.dry_run and not responses:
        logger.info("Dry-run: skipping case parsing and Excel export")
        cases = []
    elif should_resume("cases"):
        logger.info("Skipping case parsing stage (resume enabled)")
        loaded = stages.load_cases()
        if loaded is None:
            logger.warning("Case artifacts missing; re-running stage")
            cases = stages.parse_cases(responses)
        else:
            cases = loaded
    else:
        logger.info("Running case parsing stage")
        cases = stages.parse_cases(responses)

    if cases:
        stages.export_excel(cases)
    else:
        logger.info("No cases available; Excel export skipped")
