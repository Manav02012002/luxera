from __future__ import annotations

from pathlib import Path


def test_engine_modules_have_contract_header() -> None:
    root = Path(__file__).resolve().parents[2]
    engine_dir = root / "luxera" / "engine"
    py_files = sorted(p for p in engine_dir.glob("*.py") if p.name != "__init__.py")
    assert py_files, "No engine modules found"
    missing = []
    for path in py_files:
        text = path.read_text(encoding="utf-8")
        header = "\n".join(text.splitlines()[:8])
        if "Contract: docs/spec/" not in header:
            missing.append(path.name)
    assert not missing, f"Engine modules missing contract header: {missing}"
