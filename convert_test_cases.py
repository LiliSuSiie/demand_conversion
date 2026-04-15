"""
测试用例转换脚本
将 test_cases.txt 或通用 TestCase 列表转换为 ms测试用例模版.xlsx 格式
"""
from pathlib import Path
from typing import Iterable, List

import pandas as pd

from case_models import TestCase
from parser_common import cases_to_dataframe_rows


def parse_test_cases(txt_file_path: str) -> List[TestCase]:
    """
    解析 test_cases.txt 文件

    规则：
    1. 以 / 开头的行（可选前缀"数字+"）= 所属模块路径
       支持格式："/长安1.3.7/..." 或 "1. /衡水1.0/..."
    2. '• ' 开头的行 = 一条完整用例
    3. 预期结果可能跨多行（数字+点开头的续行）
    """
    import re

    with open(txt_file_path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    cases: List[TestCase] = []
    current_module = None
    current_case: TestCase | None = None

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()

        if not stripped:
            if current_case:
                cases.append(current_case)
                current_case = None
            continue

        module_match = re.match(r"^(?:(\d+)\.\s*)?(/.+)$", stripped)
        if module_match:
            if current_case:
                cases.append(current_case)
                current_case = None
            current_module = module_match.group(2).strip()
            continue

        case_match = re.match(r"^•\s*用例：(.+)$", stripped)
        if case_match:
            if current_case:
                cases.append(current_case)

            case_content = case_match.group(1)
            operation = ""
            expected = ""

            import re as _re

            op_match = _re.search(r"操作：(.+?)(?:\s*-|\s*预期：|$)", case_content)
            if op_match:
                operation = op_match.group(1).strip()

            exp_match = _re.search(r"预期：(.+)$", case_content)
            if exp_match:
                expected = exp_match.group(1).strip()

            name_parts = []
            parts = case_content.split(" - ")
            for part in parts:
                if not part.startswith("操作：") and not part.startswith("预期："):
                    name_parts.append(part.strip())

            case_name = " - ".join(name_parts)

            current_case = TestCase(
                module=current_module,
                name=case_name,
                operation=operation,
                expected=expected,
            )
            continue

        if current_case:
            import re as _re2

            is_continuation = False
            if _re2.match(r"^\d+[\.,、]\s*", stripped):
                is_continuation = True
            elif not _re2.match(r"^\d+\.\s*/", stripped) and not _re2.match(r"^•\s*用例：", stripped):
                is_continuation = True

            if is_continuation:
                current_case.expected = (
                    (current_case.expected + "\n" + stripped)
                    if current_case.expected
                    else stripped
                )
                continue

            cases.append(current_case)
            current_case = None

    if current_case:
        cases.append(current_case)

    return cases


def create_excel(cases: Iterable[TestCase], output_file: str):
    rows = cases_to_dataframe_rows(cases)
    df = pd.DataFrame(rows)
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Sheet1", index=False)
    print(f"✅ 已生成 {output_file}")
    print(f"📊 共转换 {len(rows)} 条用例")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="文本测试用例生成 Excel")
    parser.add_argument("--input", default="test_cases.txt", help="输入文本文件路径")
    parser.add_argument("--output", default="output_test_cases.xlsx", help="输出 Excel 文件路径")
    args = parser.parse_args()

    print(f"🔍 开始解析 {args.input}...")
    cases = parse_test_cases(args.input)
    print(f"📋 解析完成，共找到 {len(cases)} 条用例")

    print("\n📝 生成 Excel 文件...")
    create_excel(cases, args.output)


if __name__ == "__main__":
    main()
