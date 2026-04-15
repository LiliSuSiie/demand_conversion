from dataclasses import dataclass
from typing import Optional


@dataclass
class TestCase:
    """Standardized representation of a single test case."""

    module: Optional[str]
    name: str
    operation: str
    expected: str

    def normalize(self) -> "TestCase":
        """Trim whitespace on textual fields for consistent downstream output."""
        return TestCase(
            module=(self.module or "").strip() or None,
            name=self.name.strip(),
            operation=self.operation.strip(),
            expected=self.expected.strip(),
        )
