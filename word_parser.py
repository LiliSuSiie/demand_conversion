"""Parse structured test cases directly from Word documents."""
from __future__ import annotations

from typing import Iterable, List, Optional

from docx import Document

from case_models import TestCase


def parse_word(word_path: str) -> List[TestCase]:
    doc = Document(word_path)

    cases: List[TestCase] = []
    current_module: Optional[str] = None
    current_case: Optional[TestCase] = None

    import re

    # Word 文档主要以表格形式描述用例
    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells]
            cells = [cell for cell in cells if cell]
            if not cells:
                continue

            # 模块行：只有模块路径
            module_match = re.match(r"^(?:(\d+)\.\s*)?(/.+)$", cells[0])
            if len(cells) == 1 and module_match:
                if current_case:
                    cases.append(current_case)
                    current_case = None
                current_module = module_match.group(2).strip()
                continue

            # 用例行：包含用例名称、操作、预期
            if cells[0].startswith("• 用例："):
                if current_case:
                    cases.append(current_case)

                name_text = cells[0][len("• 用例：") :].strip()
                operation = next((c for c in cells if c.startswith("操作：")), "")
                expected = next((c for c in cells if c.startswith("预期：")), "")

                operation = operation.replace("操作：", "").strip()
                expected = expected.replace("预期：", "").strip()

                current_case = TestCase(
                    module=current_module,
                    name=name_text,
                    operation=operation,
                    expected=expected,
                )
                continue

            # 续行处理（预期结果段落）
            if current_case and len(cells) == 1:
                text = cells[0]
                if re.match(r"^\d+[\.,、]\s*", text) or not text.startswith("• 用例："):
                    current_case.expected = (
                        current_case.expected + "\n" + text
                        if current_case.expected
                        else text
                    )
                    continue

                cases.append(current_case)
                current_case = None

    if current_case:
        cases.append(current_case)

    return cases
