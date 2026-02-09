from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_PATTERNS = [
    ".DS_Store",
    "*/.DS_Store",
    ".pytest_cache/*",
    "*/.pytest_cache/*",
    "out/*",
    "*/out/*",
    "dist/*",
    "*/dist/*",
    "build/*",
    "*/build/*",
    ".venv/*",
    "*/.venv/*",
    "*__pycache__/*",
    "luxera.egg-info/*",
    "*.pyc",
    "*.pyo",
]


def _excluded(rel_path: str) -> bool:
    return any(fnmatch.fnmatch(rel_path, pat) for pat in EXCLUDE_PATTERNS)


def build_release_zip(out_path: Path) -> Path:
    out_path = out_path.expanduser().resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in ROOT.rglob("*"):
            if not p.is_file():
                continue
            rel = p.relative_to(ROOT).as_posix()
            if _excluded(rel):
                continue
            zf.write(p, rel)
    return out_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a release zip without local build/cache artifacts.")
    parser.add_argument("--out", default="dist/luxera-release.zip", help="output zip path")
    args = parser.parse_args()
    out = build_release_zip(Path(args.out))
    print(f"Release artifact written: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
