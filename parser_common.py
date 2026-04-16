from typing import Iterable, List, Optional

from case_models import TestCase


def cases_to_dataframe_rows(cases: Iterable[TestCase], *, assignee: str = "liwenqiu") -> List[dict]:
    rows = []
    for case in cases:
        normalized = case.normalize()
        rows.append(
            {
                "用例名称": normalized.name,
                "所属模块": normalized.module,
                "标签": None,
                "前置条件": None,
                "步骤描述": normalized.operation,
                "预期结果": normalized.expected,
                "编辑模式": "STEP",
                "备注": None,
                "用例状态": "未开始",
                "责任人": assignee,
                "用例等级": "P1",
            }
        )
    return rows


def serialize_to_convert_format(cases: Iterable[TestCase]) -> str:
    output_lines: List[str] = []
    current_module: Optional[str] = None

    for case in cases:
        normalized = case.normalize()
        if normalized.module and normalized.module != current_module:
            output_lines.append(normalized.module)
            current_module = normalized.module

        parts = [f"• 用例：{normalized.name}"]
        if normalized.operation:
            parts.append(f"操作：{normalized.operation}")
        if normalized.expected:
            parts.append(f"预期：{normalized.expected}")

        output_lines.append(" - ".join(parts))
        output_lines.append("")

    return "\n".join(output_lines).strip() + "\n"
