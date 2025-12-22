from __future__ import annotations

from dataclasses import dataclass
from typing import List, Protocol

from luxera.models.validation import ValidationFinding, ValidationReport
from luxera.parser.ies_parser import ParsedIES


class Rule(Protocol):
    id: str
    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]: ...


@dataclass
class Validator:
    rules: List[Rule]

    def run(self, doc: ParsedIES) -> ValidationReport:
        findings: List[ValidationFinding] = []
        for rule in self.rules:
            findings.extend(rule.evaluate(doc))
        # stable ordering: severity then id
        sev_order = {"ERROR": 0, "WARN": 1, "INFO": 2}
        findings.sort(key=lambda f: (sev_order.get(f.severity, 99), f.id))
        return ValidationReport(findings=findings)
