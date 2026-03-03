from __future__ import annotations


class LuxeraError(Exception):
    """Base exception for all Luxera errors."""

    def __init__(self, message: str, code: str, suggestion: str = ""):
        self.message = message
        self.code = code
        self.suggestion = suggestion
        super().__init__(f"[{code}] {message}")


class ProjectError(LuxeraError):
    """Errors related to project loading, saving, or validation."""


class PhotmetryError(LuxeraError):
    """Errors in photometric data parsing or sampling."""


class GeometryError(LuxeraError):
    """Errors in geometry processing."""


class CalculationError(LuxeraError):
    """Errors during calculation."""


class ComplianceError(LuxeraError):
    """Errors in compliance checking."""


class AgentError(LuxeraError):
    """Errors in agent/AI pipeline."""


ERROR_CODES = {
    "PRJ-001": "Project file not found",
    "PRJ-002": "Project schema validation failed",
    "PRJ-003": "Incompatible project version",
    "PHO-001": "Photometry file parse failed",
    "PHO-002": "Missing photometry asset",
    "PHO-003": "Invalid photometric data (negative candela)",
    "GEO-001": "Degenerate geometry (zero area surface)",
    "GEO-002": "Non-planar polygon detected",
    "GEO-003": "Room geometry not closed",
    "CAL-001": "No luminaires in project",
    "CAL-002": "No calculation grid defined",
    "CAL-003": "Radiosity solver diverged",
    "CAL-004": "All illuminance values are zero",
    "CMP-001": "Unknown compliance standard",
    "CMP-002": "Activity type not found in standard",
    "AGT-001": "LLM API key not set",
    "AGT-002": "LLM API call failed",
    "AGT-003": "No tools available for intent",
}

