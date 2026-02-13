from __future__ import annotations

from dataclasses import dataclass

from luxera.project.schema import Project


def unit_scale_to_m(unit: str) -> float:
    u = str(unit).lower()
    if u == "m":
        return 1.0
    if u == "mm":
        return 0.001
    if u == "cm":
        return 0.01
    if u == "ft":
        return 0.3048
    if u == "in":
        return 0.0254
    return 1.0


@dataclass(frozen=True)
class ParsedLength:
    value_m: float
    original_value: float
    original_unit: str


def parse_length(value: float, unit: str) -> ParsedLength:
    return ParsedLength(
        value_m=float(value) * unit_scale_to_m(unit),
        original_value=float(value),
        original_unit=str(unit),
    )


def project_scale_to_meters(project: Project) -> float:
    s = float(getattr(project.geometry, "scale_to_meters", 0.0) or 0.0)
    if s > 0.0:
        return s
    return unit_scale_to_m(getattr(project.geometry, "length_unit", "m"))
