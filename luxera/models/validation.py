from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal, Optional, Tuple, Union


Severity = Literal["ERROR", "WARN", "INFO"]
LineRef = Union[int, Tuple[int, int]]


@dataclass(frozen=True)
class ValidationFinding:
    id: str
    severity: Severity
    title: str
    message: str
    evidence: Dict[str, Any]
    line_refs: List[LineRef]
    suggested_fix: Optional[str] = None


@dataclass(frozen=True)
class ValidationReport:
    findings: List[ValidationFinding]

    @property
    def summary(self) -> Dict[str, int]:
        errors = sum(1 for f in self.findings if f.severity == "ERROR")
        warns = sum(1 for f in self.findings if f.severity == "WARN")
        info = sum(1 for f in self.findings if f.severity == "INFO")
        return {"errors": errors, "warnings": warns, "info": info}
