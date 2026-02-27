from __future__ import annotations

import re
from pathlib import Path
import sys


BANNED_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bTBD\b", re.IGNORECASE),
    re.compile(r"\bplaceholder\b", re.IGNORECASE),
    re.compile(r"\bstub\b", re.IGNORECASE),
)


SCAN_PATHS: tuple[str, ...] = (
    "luxera/engine",
    "luxera/calculation",
    "luxera/geometry",
    "tests/validation/reference_cases",
    "docs/spec/feature_matrix.md",
    "docs/spec/AGI32_PARITY.md",
)


SKIP_SUFFIXES: tuple[str, ...] = (".png", ".jpg", ".jpeg", ".gif", ".ico", ".icns", ".pdf", ".npy")


def _iter_files(root: Path, rel_path: str) -> list[Path]:
    p = root / rel_path
    if not p.exists():
        return []
    if p.is_file():
        return [p]
    out: list[Path] = []
    for f in p.rglob("*"):
        if not f.is_file():
            continue
        if f.suffix.lower() in SKIP_SUFFIXES:
            continue
        out.append(f)
    return sorted(out)


def run_guard(root: Path) -> list[str]:
    violations: list[str] = []
    for rel in SCAN_PATHS:
        for path in _iter_files(root, rel):
            try:
                text = path.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                for pat in BANNED_PATTERNS:
                    if pat.search(line):
                        violations.append(f"{path}:{i}: banned term '{pat.pattern}'")
    return violations


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    violations = run_guard(root)
    if violations:
        print("No-scaffold guard failed. Remove placeholder/scaffold terms from guarded paths:")
        for v in violations:
            print(f" - {v}")
        return 1
    print("No-scaffold guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
