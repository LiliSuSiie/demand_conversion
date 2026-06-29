"""Prompt helper for converting requirements into LLM-ready chunks and parsing outputs."""
from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence

from case_models import TestCase
from requirement_models import RequirementBlock


class PreviewFormat:
    PRETTY = "pretty"
    RAW = "raw"


def _parse_requirement_tables(docx_path: Path) -> List[RequirementBlock]:
    from requirement_parser import parse_requirement_tables

    return parse_requirement_tables(docx_path)


def _write_preview_file(
    docx_path: Path,
    preview_path: Path,
    blocks: Sequence[RequirementBlock],
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



DEFAULT_DOCX = Path("source/wordv1.3.7.docx")
DEFAULT_PROMPT_JSON = Path("requirements_prompt.json")
DEFAULT_REQUIREMENTS_JSON = Path("requirements.json")
DEFAULT_PREVIEW_MD = Path("requirements_preview.md")
DEFAULT_BATCH_SIZE = 5
CHUNK_SEPARATOR = "\n================\n"
LLM_CONVERT_REGEX = re.compile(
    r"^[•*-]\s*用例：(?P<name>.+?)\s*-\s*操作：(?P<operation>.+?)\s*-\s*预期：(?P<expected>.+?)$"
)

PROMPT_HEADER = """### LLM Prompt
你是一名专业的软件测试工程师，需要将下述需求转化为 Convert.txt 格式的测试用例。
要求：严格遵守 /模块 + “• 用例：… - 操作：… - 预期：…” 结构，可产出多条用例，不要额外解释。
"""

CHUNK_TEMPLATE = """#### 模块：{module}
主题：{title}
需求描述：
{description}
"""

OUTPUT_INSTRUCTIONS = """### 输出格式
```
/模块路径
• 用例：名称 - 操作：具体步骤 - 预期：系统表现
```
可包含多条用例。
"""

INGEST_HELP = """### Convert.txt 解析提示
1. 确认模型输出顶部带有 /模块 路径。
2. 每条用例包含“• 用例：”“操作：”“预期：”字段。
3. 使用 `generate_requirement_prompts.py ingest-output` 将文本转换为 JSON，再交给 convert_test_cases.py。
"""


@dataclass
class PromptChunk:
    index: int
    requirements: Sequence[RequirementBlock]
    context: str = ""

    def render(self) -> str:
        lines = [f"### Chunk {self.index} ({len(self.requirements)} requirements)"]
        if self.context:
            lines.append("### 业务流程背景（供参考，用于生成端到端测试用例）")
            lines.append(self.context.strip())
            lines.append("")
        lines.append(PROMPT_HEADER.strip())
        for block in self.requirements:
            lines.append(
                CHUNK_TEMPLATE.format(
                    module=block.module,
                    title=block.title,
                    description=block.description.strip(),
                ).strip()
            )
            if block.notes:
                lines.append("备注：" + block.notes.strip())
            if block.segments:
                lines.append("分段：")
                lines.extend(f"- {segment}" for segment in block.segments)
            lines.append("")
        lines.append(OUTPUT_INSTRUCTIONS.strip())
        lines.append("\n---\n")
        lines.append("请在此处粘贴模型 Convert.txt 输出：")
        lines.append("````text\n/模块示例\n• 用例：示例 - 操作：示例步骤 - 预期：示例预期\n````")
        lines.append(INGEST_HELP.strip())
        return "\n".join(lines)


class PromptGenerator:
    def __init__(self, blocks: Sequence[RequirementBlock], context: str = ""):
        self.blocks = list(blocks)
        self.context = context

    def chunk(self, batch_size: int) -> List[PromptChunk]:
        chunks: List[PromptChunk] = []
        for idx in range(0, len(self.blocks), batch_size):
            chunk = PromptChunk(
                index=idx // batch_size + 1,
                requirements=self.blocks[idx : idx + batch_size],
                context=self.context,
            )
            chunks.append(chunk)
        return chunks

    def render(self, batch_size: int) -> str:
        return CHUNK_SEPARATOR.join(chunk.render() for chunk in self.chunk(batch_size))


class LLMOutputParser:
    def __init__(self, text: str):
        self.text = text

    def parse(self) -> List[TestCase]:
        cases: List[TestCase] = []
        current_module: Optional[str] = None
        for raw_line in self.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("/"):
                current_module = line
                continue
            match = LLM_CONVERT_REGEX.match(line)
            if match and current_module:
                cases.append(
                    TestCase(
                        module=current_module,
                        name=match.group("name").strip(),
                        operation=match.group("operation").strip(),
                        expected=match.group("expected").strip(),
                    )
                )
        return cases


def load_requirement_blocks(docx_path: Optional[Path], prompt_json: Optional[Path]) -> List[RequirementBlock]:
    if prompt_json and prompt_json.exists():
        data = json.loads(prompt_json.read_text(encoding="utf-8"))
        requirements = data.get("requirements", data)
        blocks = []
        for item in requirements:
            blocks.append(
                RequirementBlock(
                    module=item.get("module", ""),
                    title=item.get("title", ""),
                    description=item.get("description", ""),
                    notes=item.get("notes"),
                    block_id=item.get("block_id"),
                    table_index=item.get("table_index"),
                    row_index=item.get("row_index"),
                    segments=item.get("segments"),
                )
            )
        return blocks

    if docx_path and docx_path.exists():
        return _parse_requirement_tables(docx_path)

    raise SystemExit("No valid source provided (docx or prompt JSON)")


def emit_prompts(args: argparse.Namespace) -> None:
    docx_path = Path(args.docx) if args.docx else DEFAULT_DOCX
    prompt_json = Path(args.prompt_json) if args.prompt_json else None

    if getattr(args, "validate_docx", False) and docx_path:
        validate_docx(docx_path, Path(args.requirements_json), Path(args.preview_md), args.encoding)

    blocks = load_requirement_blocks(docx_path, prompt_json)
    if not blocks:
        raise SystemExit("No requirement blocks available for prompt generation")

    generator = PromptGenerator(blocks)
    rendered = generator.render(batch_size=args.batch_size)
    if args.output:
        Path(args.output).write_text(rendered, encoding=args.encoding)
    else:
        print(rendered)


def validate_docx(docx_path: Path, json_path: Path, preview_path: Path, encoding: str) -> None:
    if not docx_path.exists():
        raise SystemExit(f"DOCX file not found: {docx_path}")

    blocks = _parse_requirement_tables(docx_path)
    if not blocks:
        raise SystemExit("No requirement blocks were parsed from the document.")

    payload = json.dumps([block.as_dict() for block in blocks], ensure_ascii=False, indent=2) + "\n"
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(payload, encoding=encoding)

    _write_preview_file(
        docx_path,
        preview_path,
        blocks,
        block_limit=10,
        paragraph_limit=8,
        encoding=encoding,
        format=PreviewFormat.PRETTY,
    )

    print(f"Validated DOCX: {docx_path}\n- JSON: {json_path}\n- Preview: {preview_path}")


def ingest_output(args: argparse.Namespace) -> None:
    input_text = Path(args.input).read_text(encoding=args.encoding)
    parser = LLMOutputParser(input_text)
    cases = parser.parse()
    if not cases:
        raise SystemExit("No test cases parsed from LLM output")

    payload = {
        "cases": [case.normalize().__dict__ for case in cases],
        "total": len(cases),
    }

    output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Requirement prompt helper")
    subparsers = parser.add_subparsers(dest="command", required=True)

    emit_parser = subparsers.add_parser("emit-prompts", help="Generate prompt chunks")
    emit_parser.add_argument("--docx", type=str, help="Word source path", default=str(DEFAULT_DOCX))
    emit_parser.add_argument("--prompt-json", type=str, help="Existing prompt JSON output")
    emit_parser.add_argument(
        "--requirements-json",
        type=str,
        default=str(DEFAULT_REQUIREMENTS_JSON),
        help="Destination for validated requirements JSON",
    )
    emit_parser.add_argument(
        "--preview-md",
        type=str,
        default=str(DEFAULT_PREVIEW_MD),
        help="Destination for validation preview markdown",
    )
    emit_parser.add_argument(
        "--validate-docx",
        action="store_true",
        help="Validate DOCX before emitting prompts",
    )
    emit_parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Requirements per chunk")
    emit_parser.add_argument("--output", type=str, help="Destination for rendered prompt text")
    emit_parser.add_argument("--encoding", type=str, default="utf-8")
    emit_parser.set_defaults(func=emit_prompts)

    validate_parser = subparsers.add_parser("validate-docx", help="Validate DOCX and emit artifacts")
    validate_parser.add_argument("--docx", type=str, default=str(DEFAULT_DOCX), help="Word source path")
    validate_parser.add_argument(
        "--output-json",
        type=str,
        default=str(DEFAULT_REQUIREMENTS_JSON),
        help="Destination for requirements JSON",
    )
    validate_parser.add_argument(
        "--preview-md",
        type=str,
        default=str(DEFAULT_PREVIEW_MD),
        help="Destination for preview markdown",
    )
    validate_parser.add_argument("--encoding", type=str, default="utf-8")
    validate_parser.set_defaults(
        func=lambda args: validate_docx(
            Path(args.docx), Path(args.output_json), Path(args.preview_md), args.encoding
        )
    )

    ingest_parser = subparsers.add_parser("ingest-output", help="Normalize LLM output")
    ingest_parser.add_argument("--input", required=True, help="Path to LLM output text")
    ingest_parser.add_argument("--output", help="Destination JSON for parsed cases")
    ingest_parser.add_argument("--encoding", default="utf-8")
    ingest_parser.set_defaults(func=ingest_output)

    return parser


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
