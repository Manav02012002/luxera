from __future__ import annotations

from pathlib import Path


def test_required_spec_docs_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    required = [
        "docs/spec/coordinate_conventions.md",
        "docs/spec/photometry_contracts.md",
        "docs/spec/solver_contracts.md",
        "docs/spec/validation_policy.md",
        "docs/spec/report_contracts.md",
        "docs/spec/roadway_grid_definition.md",
        "docs/spec/daylight_contract.md",
        "docs/spec/emergency_contract.md",
    ]
    missing = [p for p in required if not (root / p).exists()]
    assert not missing, f"Missing required spec docs: {missing}"
