from __future__ import annotations

import math
from typing import List

from luxera.models.validation import ValidationFinding
from luxera.parser.ies_parser import ParsedIES


class RuleNegativeCandela:
    id = "LUXERA_CDL_NEGATIVE"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.candela is None:
            return []
        if not doc.candela.has_negative:
            return []
        return [
            ValidationFinding(
                id=self.id,
                severity="ERROR",
                title="Negative candela values",
                message="Candela table contains negative values, which is usually invalid photometric data.",
                evidence={"min_cd": doc.candela.min_cd},
                line_refs=[doc.candela.line_span],
                suggested_fix="Verify the IES file source or request corrected photometry from the manufacturer.",
            )
        ]


class RuleNanInfCandela:
    id = "LUXERA_CDL_NAN_INF"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.candela is None:
            return []
        if not doc.candela.has_nan_or_inf:
            return []
        return [
            ValidationFinding(
                id=self.id,
                severity="ERROR",
                title="NaN/Inf candela values",
                message="Candela table contains NaN or Infinity values.",
                evidence={},
                line_refs=[doc.candela.line_span],
                suggested_fix="Verify the IES file integrity and re-export if possible.",
            )
        ]


class RuleCandelaMultiplierNotOne:
    id = "LUXERA_HDR_CDL_MULT"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.photometry is None:
            return []
        m = doc.photometry.candela_multiplier
        if abs(m - 1.0) < 1e-12:
            return []
        return [
            ValidationFinding(
                id=self.id,
                severity="INFO",
                title="Candela multiplier is not 1",
                message="This IES file uses a candela multiplier; Luxera applies it to produce scaled candela values.",
                evidence={"candela_multiplier": m},
                line_refs=[doc.photometry.line_no],
                suggested_fix=None,
            )
        ]


class RuleAnglesRangeInfo:
    id = "LUXERA_ANG_RANGE"

    def evaluate(self, doc: ParsedIES) -> List[ValidationFinding]:
        if doc.angles is None:
            return []
        v = doc.angles.vertical_deg
        h = doc.angles.horizontal_deg
        return [
            ValidationFinding(
                id=self.id,
                severity="INFO",
                title="Angle ranges detected",
                message="Vertical and horizontal angle ranges were parsed successfully.",
                evidence={
                    "vertical_min": v[0],
                    "vertical_max": v[-1],
                    "horizontal_min": h[0],
                    "horizontal_max": h[-1],
                },
                line_refs=[doc.angles.vertical_line_span, doc.angles.horizontal_line_span],
            )
        ]
