from __future__ import annotations

from pathlib import Path

from scripts.no_scaffold_guard import run_guard


def test_no_scaffold_policy() -> None:
    root = Path(__file__).resolve().parents[2]
    violations = run_guard(root)
    assert not violations, "No-scaffold policy violations:\n" + "\n".join(violations)
