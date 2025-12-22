from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from luxera.derived.metrics import compute_derived_metrics
from luxera.models.derived import DerivedMetrics
from luxera.models.validation import ValidationReport
from luxera.parser.ies_parser import ParsedIES, parse_ies_text
from luxera.validation.defaults import default_validator


@dataclass(frozen=True)
class LuxeraViewResult:
    doc: ParsedIES
    derived: Optional[DerivedMetrics]
    report: Optional[ValidationReport]


def parse_and_analyse_ies(text: str) -> LuxeraViewResult:
    doc = parse_ies_text(text)

    derived = None
    report = None

    if doc.angles is not None and doc.candela is not None:
        derived = compute_derived_metrics(doc.angles, doc.candela)
        report = default_validator().run(doc)

    return LuxeraViewResult(doc=doc, derived=derived, report=report)
